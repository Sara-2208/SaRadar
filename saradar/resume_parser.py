"""Resume parsing (v2): two-pass, privacy-first.

Pipeline:
1. extract_text()  -> raw text from PDF
2. remove REFERENCES section (never store referees' details)
3. mask ALL emails/phones locally before any LLM call
4. pass A (header, summary, skills, experience) + pass B (education,
   projects, activities, certifications, languages)
5. completeness check -> retry a pass once with tier="smart" if a section
   heading exists but came back empty
6. restore the candidate's own email/phone, return Profile + warnings
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import pdfplumber
from pydantic import ValidationError

from saradar import llm as llm_mod
from saradar.schemas import EMAIL_RE, PHONE_RE, Profile, ScannedPDFError

logger = logging.getLogger("saradar.resume_parser")


# ---------------------------------------------------------------------------
# 1. Text extraction
# ---------------------------------------------------------------------------


def extract_text(source: Union[bytes, str, Path]) -> str:
    """Extract plain text from PDF bytes or a file path.

    Raises:
        ScannedPDFError: if under 200 characters (likely image-only PDF).
    """
    pdf_obj = open(str(source), "rb") if isinstance(source, (str, Path)) else io.BytesIO(source)
    try:
        with pdfplumber.open(pdf_obj) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages).strip()
    finally:
        try:
            pdf_obj.close()
        except Exception:  # pragma: no cover
            pass

    if len(text) < 200:
        raise ScannedPDFError(
            "PDF looks scanned / image-only, no extractable text. "
            "Please OCR it first or paste text directly."
        )
    return text


# ---------------------------------------------------------------------------
# 2. Privacy helpers
# ---------------------------------------------------------------------------

_REFERENCES_RE = re.compile(r"(?im)^[ \t]*(references|referees)\b[^\n]*$")
_PLACEHOLDERS = {"[EMAIL]", "[PHONE]"}


def _strip_references(text: str) -> str:
    """Drop the REFERENCES section and everything after it."""
    match = _REFERENCES_RE.search(text)
    return text[: match.start()].rstrip() if match else text


def _extract_and_mask_pii(text: str) -> Tuple[str, List[str], List[str]]:
    """Replace every email/phone with [EMAIL]/[PHONE]; return originals in order."""
    emails: List[str] = []
    phones: List[str] = []

    def _email_sub(m: re.Match) -> str:
        emails.append(m.group(0))
        return "[EMAIL]"

    def _phone_sub(m: re.Match) -> str:
        val = m.group(0)
        if len(re.sub(r"\D", "", val)) < 7:  # probably a year or small number
            return val
        phones.append(val)
        return "[PHONE]"

    masked = EMAIL_RE.sub(_email_sub, text)
    masked = PHONE_RE.sub(_phone_sub, masked)
    return masked, emails, phones


def _restore_pii(profile: Profile, emails: List[str], phones: List[str]) -> Profile:
    """Put back ONLY the candidate's own contact (first found, near the top)."""
    data = profile.model_dump()
    if emails:
        data["email"] = emails[0]
    elif data.get("email") in _PLACEHOLDERS:
        data["email"] = None
    if phones:
        data["phone"] = phones[0]
    elif data.get("phone") in _PLACEHOLDERS:
        data["phone"] = None
    return Profile.model_validate(data)


# ---------------------------------------------------------------------------
# 3. Prompts for the two passes
# ---------------------------------------------------------------------------

_BASE_RULES = (
    "You are a precise resume parser. Extract ONLY information literally written "
    "in the resume text. Never invent, infer, or guess anything. Keep the original "
    "wording of bullet points; do not rephrase or embellish. Use null for missing "
    "text fields and [] for missing lists. Emails and phone numbers are masked as "
    "[EMAIL] and [PHONE]; copy the placeholder for the candidate's own contact. "
    "Respond in JSON only."
)

_PASS_A: Dict[str, Any] = {
    "name": "A",
    "keys": ["name", "headline", "email", "phone", "location", "links",
             "summary", "skills", "experience"],
    "instructions": (
        "PASS A: extract the header, summary, skills and work experience. "
        "headline = the short title line under the name, if any. "
        "links = GitHub, LinkedIn or portfolio handles/URLs exactly as written. "
        "skills.technical = programming languages; skills.tools = frameworks, "
        "tools, databases, platforms and software; skills.soft = soft skills only "
        "if explicitly listed. Include EVERY job in experience, in the order written."
    ),
    "skeleton": (
        '{"name": null, "headline": null, "email": null, "phone": null, '
        '"location": null, "links": {"github": null, "linkedin": null, "portfolio": null}, '
        '"summary": null, "skills": {"technical": [], "tools": [], "soft": []}, '
        '"experience": [{"title": null, "company": null, "location": null, '
        '"start": null, "end": null, "bullets": []}]}'
    ),
}

_PASS_B: Dict[str, Any] = {
    "name": "B",
    "keys": ["education", "projects", "activities", "certifications", "languages"],
    "instructions": (
        "PASS B: extract education, projects, activities, certifications and "
        "spoken languages. Include EVERY entry of each section, in the order written. "
        "education: every degree or programme, with its bullets. "
        "projects: personal/academic projects AND competitions/hackathons; put a "
        "placement such as 'Champion' or 'Top 10 Finalist' in result, a level such as "
        "'National Level' in level, and the month/year in date. "
        "activities: leadership roles, committees, volunteering, events, and "
        "exchange or international programmes. "
        "languages: spoken languages only, never programming languages."
    ),
    "skeleton": (
        '{"education": [{"degree": null, "field": null, "institution": null, '
        '"start": null, "end": null, "grade": null, "bullets": []}], '
        '"projects": [{"name": null, "role": null, "result": null, "level": null, '
        '"date": null, "description": null, "tech": []}], '
        '"activities": [{"title": null, "organization": null, "role": null, '
        '"start": null, "end": null, "bullets": []}], '
        '"certifications": [], "languages": []}'
    ),
}


# ---------------------------------------------------------------------------
# 4. Completeness check
# ---------------------------------------------------------------------------


def _heading(words: str) -> re.Pattern:
    """Match a heading line: up to 2 leading words, then one of `words`."""
    return re.compile(rf"(?im)^[ \t•\-]*(?:[a-z&]+[ \t]+){{0,2}}(?:{words})\b")


_HEADINGS: Dict[str, re.Pattern] = {
    "experience": _heading("experience"),
    "skills": _heading("skills"),
    "education": _heading("education"),
    "projects": _heading(r"projects?|competitions?"),
    "activities": _heading(r"leadership|activities|exposure|volunteer\w*|exchange"),
    "certifications": _heading(r"certifications?|certificates?"),
    "languages": _heading(r"languages?"),
}


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, dict):  # e.g. skills
        return all(_is_empty(v) for v in value.values())
    if isinstance(value, (list, str)):
        return len(value) == 0
    return False


def _missing_sections(keys: List[str], data: Dict[str, Any], text: str) -> List[str]:
    """Sections whose heading appears in the text but came back empty."""
    return [
        k for k in keys
        if k in _HEADINGS and _HEADINGS[k].search(text) and _is_empty(data.get(k))
    ]


# ---------------------------------------------------------------------------
# 5. Running one pass
# ---------------------------------------------------------------------------


def _run_pass(spec: Dict[str, Any], masked_text: str, tier: str) -> Tuple[Dict[str, Any], llm_mod.LLMResult]:
    """Run one extraction pass; validate; retry once on validation error."""
    keys: List[str] = spec["keys"]
    system = (
        f"{_BASE_RULES}\n{spec['instructions']}\n"
        f"Return ONLY a JSON object with exactly these keys:\n{spec['skeleton']}"
    )
    user = f"RESUME TEXT:\n{masked_text}\n\nReturn the JSON object now."

    def _validate(raw: Any) -> Dict[str, Any]:
        raw = raw if isinstance(raw, dict) else {}
        partial = {k: raw[k] for k in keys if k in raw}
        return Profile.model_validate(partial).model_dump(include=set(keys))

    raw, result = llm_mod.complete_json(user, system=system, tier=tier)
    try:
        return _validate(raw), result
    except ValidationError as err:
        logger.warning("Pass %s failed validation, retrying once", spec["name"])
        retry_user = (
            f"{user}\n\nPrevious JSON failed validation. Errors: {err.errors()!r}. "
            "Fix it and return valid JSON."
        )
        raw, result = llm_mod.complete_json(retry_user, system=system, tier=tier)
        return _validate(raw), result  # raises ValidationError if still bad


# ---------------------------------------------------------------------------
# 6. Public API
# ---------------------------------------------------------------------------


@dataclass
class ParseOutcome:
    profile: Profile
    results: List[llm_mod.LLMResult]
    warnings: List[str] = field(default_factory=list)

    @property
    def models_used(self) -> List[str]:
        return sorted({r.model_used for r in self.results})


def parse_resume_full(text: str) -> ParseOutcome:
    """Full parse with warnings. Use this in the UI and scripts."""
    if not text or not text.strip():
        raise ValueError("Empty resume text, cannot parse.")

    cleaned = _strip_references(text)
    masked, emails, phones = _extract_and_mask_pii(cleaned)

    merged: Dict[str, Any] = {}
    results: List[llm_mod.LLMResult] = []
    warnings: List[str] = []

    for spec in (_PASS_A, _PASS_B):
        data, result = _run_pass(spec, masked, tier="fast")
        results.append(result)

        missing = _missing_sections(spec["keys"], data, masked)
        if missing:
            logger.info("Pass %s missing %s, retrying with smart tier", spec["name"], missing)
            try:
                data2, result2 = _run_pass(spec, masked, tier="smart")
                results.append(result2)
                for k in spec["keys"]:
                    if _is_empty(data.get(k)) and not _is_empty(data2.get(k)):
                        data[k] = data2[k]
            except (llm_mod.AllModelsFailed, ValidationError) as exc:
                logger.warning("Smart retry for pass %s failed: %s", spec["name"], exc)
            missing = _missing_sections(spec["keys"], data, masked)

        warnings += [
            f"{k.capitalize()} section may be missing. Please check and add it manually."
            for k in missing
        ]
        merged.update(data)

    profile = _restore_pii(Profile.model_validate(merged), emails, phones)
    return ParseOutcome(profile=profile, results=results, warnings=warnings)


def parse_resume(text: str) -> Tuple[Profile, llm_mod.LLMResult]:
    """Backwards-compatible wrapper: returns (profile, first LLMResult)."""
    outcome = parse_resume_full(text)
    return outcome.profile, outcome.results[0]