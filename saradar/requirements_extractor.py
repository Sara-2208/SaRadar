"""Job description -> structured JobRequirements (Phase 3A).

The LLM only extracts what is written. Known metadata (title, company,
location from the job API) always wins over LLM guesses.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from pydantic import ValidationError

from saradar import llm as llm_mod
from saradar.schemas import JobRequirements

logger = logging.getLogger("saradar.requirements")

# JDs shorter than this are usually summaries (e.g. JobLeads, Trabajo snippets)
MIN_FULL_JD_CHARS = 600

_SYSTEM = (
    "You extract hiring requirements from a job description. Use ONLY what is "
    "written; never invent skills or requirements. "
    "must_have_skills = concrete skills, tools or technologies stated as required. "
    "nice_to_have_skills = stated as preferred, a plus, an advantage, a bonus, or nice to have. "
    "Keep skill names short (e.g. 'Python', 'LangChain', 'AWS'), never full sentences. "
    "seniority = one of Intern, Entry, Junior, Mid, Senior, Lead, Manager, or null if unclear. "
    "years_experience_min = minimum years required as an integer, or null. "
    "work_mode = On-site, Hybrid, Remote, or null. "
    "employment_type = Full-time, Part-time, Contract, Internship, or null. "
    "responsibilities = up to 8 short points in the original wording. "
    "Respond in JSON only with exactly these keys: "
    '{"title": null, "company": null, "location": null, "work_mode": null, '
    '"employment_type": null, "seniority": null, "years_experience_min": null, '
    '"must_have_skills": [], "nice_to_have_skills": [], "education": null, '
    '"responsibilities": []}'
)


def _dedupe(items: List[str]) -> List[str]:
    seen, out = set(), []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


def _validate(raw) -> JobRequirements:
    return JobRequirements.model_validate(raw if isinstance(raw, dict) else {})


def extract_requirements(
    jd_text: str,
    title: Optional[str] = None,
    company: Optional[str] = None,
    location: Optional[str] = None,
) -> Tuple[JobRequirements, llm_mod.LLMResult]:
    """Extract structured requirements from a job description."""
    if not jd_text or not jd_text.strip():
        raise ValueError("Empty job description, cannot extract requirements.")

    jd = jd_text.strip()
    hints = "".join(
        f"KNOWN {label}: {value}\n"
        for label, value in (("TITLE", title), ("COMPANY", company), ("LOCATION", location))
        if value
    )
    user = f"{hints}JOB DESCRIPTION:\n{jd}\n\nReturn the JSON object now."

    raw, result = llm_mod.complete_json(user, system=_SYSTEM, tier="fast")
    try:
        req = _validate(raw)
    except ValidationError as err:
        logger.warning("Requirements failed validation, retrying once")
        raw, result = llm_mod.complete_json(
            f"{user}\n\nPrevious JSON failed validation: {err.errors()!r}. Fix it.",
            system=_SYSTEM,
            tier="fast",
        )
        req = _validate(raw)

    must = _dedupe(req.must_have_skills)
    must_lower = {m.lower() for m in must}
    nice = [s for s in _dedupe(req.nice_to_have_skills) if s.lower() not in must_lower]

    known = {k: v for k, v in {"title": title, "company": company, "location": location}.items() if v}
    req = req.model_copy(update={
        **known,
        "must_have_skills": must,
        "nice_to_have_skills": nice,
        "jd_quality": "full" if len(jd) >= MIN_FULL_JD_CHARS else "partial",
    })
    return req, result