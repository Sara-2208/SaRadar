"""Job description requirements extractor.

Turns free-text job descriptions into structured requirements: required vs
nice-to-have skills, years of experience, education level, location/work-mode
constraints, etc.
"""

from typing import Any, Dict, List

# TODO: Use LLM extract_json with a strict schema for consistent output
# TODO: Add a rule-based fallback if LLM is unavailable
# TODO: Cache extraction results keyed by JD hash


def extract_requirements(jd_text: str) -> Dict[str, Any]:
    """Extract structured requirements from a job description.

    Args:
        jd_text: Raw job description text.

    Returns:
        Dict with keys such as:
        - required_skills: List[str]
        - nice_to_have_skills: List[str]
        - min_years_experience: int | None
        - education_level: str | None
        - work_mode: "remote" | "hybrid" | "onsite" | None
        - certifications: List[str]
        - domain_keywords: List[str]
    """
    # TODO: Design a robust JSON schema for extraction
    # TODO: Prompt the LLM with the schema + examples
    # TODO: Validate output and retry on schema mismatch
    raise NotImplementedError("extract_requirements() is a placeholder. #TODO: LLM-based structured extraction")


def normalize_skill(skill: str) -> str:
    """Normalize a skill name for matching.

    Examples: "Python 3" -> "python", "PyTorch / Torch" -> "pytorch".

    Args:
        skill: Raw skill string from extraction.

    Returns:
        Lowercased, canonicalized skill name.
    """
    # TODO: Build a skill alias map (e.g. "torch" <-> "pytorch")
    # TODO: Use fuzzy matching against skills taxonomy
    raise NotImplementedError("normalize_skill() is a placeholder. #TODO: skill normalization + alias map")


def skills_match_score(candidate_skills: List[str], required_skills: List[str]) -> float:
    """Compute how many required skills the candidate has.

    Args:
        candidate_skills: Normalized skills from the candidate profile.
        required_skills: Normalized required skills from the JD.

    Returns:
        Float in [0, 1] representing the fraction of required skills covered.
    """
    # TODO: Use sentence-transformer embeddings for semantic (not just exact) match
    # TODO: Weight mission-critical skills higher
    raise NotImplementedError("skills_match_score() is a placeholder. #TODO: semantic skill overlap scoring")
