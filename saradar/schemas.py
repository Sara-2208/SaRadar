"""Pydantic v2 schemas for SaRadar.

All fields are optional. A shared before-validator:
- turns null list fields into []
- turns comma-separated strings into lists for simple string-list fields
- folds a flat ``skills`` list into ``skills.technical``
- turns null ``skills`` / ``links`` objects into {}
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

class ScannedPDFError(ValueError):
    """Raised when a PDF has no extractable text (likely a scan)."""


# ---------------------------------------------------------------------------
# Regex + masking helpers (shared with resume_parser)
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[\s\-.()]?)?(?:\(?\d{2,4}\)?[\s\-.]?)?\d{3,4}[\s\-.]?\d{3,4}(?!\w)"
)


def mask_email(email: str) -> str:
    """``foo.bar@gmail.com`` -> ``f******@gmail.com``."""
    if not email:
        return email
    local, _, domain = email.partition("@")
    if not local or not domain:
        return email
    return f"{local[0]}{'*' * max(1, len(local) - 1)}@{domain}"


def mask_phone(phone: str) -> str:
    """``+60 12-345 6789`` -> ``+60 ***``."""
    if not phone:
        return phone
    digits = "".join(re.findall(r"\d+", phone))
    if not digits:
        return phone
    keep_n = min(3, max(1, len(digits) - 6)) if len(digits) > 5 else 1
    return f"+{digits[:keep_n]} ***"


# ---------------------------------------------------------------------------
# Shared before-validator
# ---------------------------------------------------------------------------

_OBJECT_LIST_FIELDS = {"experience", "education", "projects", "activities"}
_STRING_LIST_FIELDS = {"technical", "tools", "soft", "tech", "certifications", "languages",
                       "must_have_skills", "nice_to_have_skills"}
_TEXT_LIST_FIELDS = {"bullets", "responsibilities"}
_OBJECT_FIELDS = {"skills", "links"}


def _normalize_before(data: Any) -> Any:
    """Clean messy LLM output before Pydantic validates it."""
    if data is None:
        return {}
    if not isinstance(data, dict):
        return data

    result = dict(data)

    # Flat skills list -> skills.technical
    if isinstance(result.get("skills"), list):
        result["skills"] = {"technical": list(result["skills"])}

    # Links given as a list -> map to github / linkedin / portfolio
    if isinstance(result.get("links"), list):
        links: dict[str, str] = {}
        for item in result["links"]:
            s = str(item)
            low = s.lower()
            if "github" in low:
                links.setdefault("github", s)
            elif "linkedin" in low:
                links.setdefault("linkedin", s)
            else:
                links.setdefault("portfolio", s)
        result["links"] = links

    for key, value in list(result.items()):
        if value is None:
            if key in _OBJECT_LIST_FIELDS | _STRING_LIST_FIELDS | _TEXT_LIST_FIELDS:
                result[key] = []
            elif key in _OBJECT_FIELDS:
                result[key] = {}
        elif isinstance(value, str):
            if key in _STRING_LIST_FIELDS:
                result[key] = [p.strip() for p in value.split(",") if p.strip()]
            elif key in _TEXT_LIST_FIELDS:
                result[key] = [value.strip()] if value.strip() else []
        elif isinstance(value, list) and key in _STRING_LIST_FIELDS | _TEXT_LIST_FIELDS:
            result[key] = [str(v).strip() for v in value if v is not None and str(v).strip()]
    return result


class _Base(BaseModel):
    """All SaRadar models share the same cleaning step."""

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        return _normalize_before(data)


# ---------------------------------------------------------------------------
# Nested models
# ---------------------------------------------------------------------------


class SkillGroup(_Base):
    technical: list[str] = []
    tools: list[str] = []
    soft: list[str] = []


class Links(_Base):
    github: str | None = None
    linkedin: str | None = None
    portfolio: str | None = None


class ExperienceEntry(_Base):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    start: str | None = None
    end: str | None = None
    bullets: list[str] = []


class EducationEntry(_Base):
    degree: str | None = None
    field: str | None = None
    institution: str | None = None
    start: str | None = None
    end: str | None = None
    grade: str | None = None
    bullets: list[str] = []


class ProjectEntry(_Base):
    name: str | None = None
    role: str | None = None
    result: str | None = None      # e.g. "Champion", "Top 10 Finalist"
    level: str | None = None       # e.g. "National Level"
    date: str | None = None
    description: str | None = None
    tech: list[str] = []


class ActivityEntry(_Base):
    title: str | None = None
    organization: str | None = None
    role: str | None = None
    start: str | None = None
    end: str | None = None
    bullets: list[str] = []


# ---------------------------------------------------------------------------
# Top-level Profile
# ---------------------------------------------------------------------------


class Profile(_Base):
    """Structured candidate profile. Missing = None (text) or [] (lists)."""

    name: str | None = None
    headline: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: Links = Field(default_factory=Links)
    summary: str | None = None
    skills: SkillGroup = Field(default_factory=SkillGroup)
    experience: list[ExperienceEntry] = []
    education: list[EducationEntry] = []
    projects: list[ProjectEntry] = []
    activities: list[ActivityEntry] = []
    certifications: list[str] = []
    languages: list[str] = []

    def all_skills(self) -> list[str]:
        """Lowercased, deduplicated technical + tools skills."""
        seen: set[str] = set()
        out: list[str] = []
        for skill in list(self.skills.technical) + list(self.skills.tools):
            key = skill.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(key)
        return out

    def masked_dump(self) -> dict:
        """model_dump() with email and phone masked, safe to print/share."""
        d = self.model_dump(mode="json")
        if d.get("email"):
            d["email"] = mask_email(d["email"])
        if d.get("phone"):
            d["phone"] = mask_phone(d["phone"])
        return d

# ---------------------------------------------------------------------------
# Job requirements (Phase 3)
# ---------------------------------------------------------------------------


class JobRequirements(_Base):
    """Structured requirements extracted from a job description."""

    title: str | None = None
    company: str | None = None
    location: str | None = None
    work_mode: str | None = None          # On-site / Hybrid / Remote
    employment_type: str | None = None    # Full-time / Part-time / Contract / Internship
    seniority: str | None = None          # Intern / Entry / Junior / Mid / Senior / Lead / Manager
    years_experience_min: int | None = None
    must_have_skills: list[str] = []
    nice_to_have_skills: list[str] = []
    education: str | None = None
    responsibilities: list[str] = []
    jd_quality: str = "full"              # "full" or "partial" (short summary JDs)

    @field_validator("years_experience_min", mode="before")
    @classmethod
    def _parse_years(cls, v: Any) -> Any:
        """'3-5 years' -> 3, '2+' -> 2, None stays None."""
        if v is None or isinstance(v, int):
            return v
        match = re.search(r"\d+", str(v))
        return int(match.group()) if match else None