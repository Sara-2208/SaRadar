"""Resume tailoring module.

Given a candidate profile and a target job description, produces a tailored
resume draft (bullet point rewrites, ordering, highlights).

IMPORTANT RULE: Never invent experience. Tailoring = rephrase + reorder
existing bullets, never fabricate achievements or roles.
"""

from typing import Any, Dict, List

# TODO: Design bullet-rephrasing prompt that forbids fabrication
# TODO: Add validation step ensuring every output bullet maps to an input bullet
# TODO: Support multiple output formats (text, JSON bullets, DOCX template fill)


def tailor_bullets(
    original_bullets: List[str],
    job_requirements: Dict[str, Any],
    job_title: str,
) -> List[Dict[str, Any]]:
    """Rewrite and reorder experience bullets to match a target job.

    **Never invent experience.** Every output bullet must be traceable to an
    input bullet. Output includes the original_bullet_index for auditability.

    Args:
        original_bullets: List of original achievement bullets (one experience entry).
        job_requirements: Structured requirements extracted from the JD.
        job_title: Target job title for context.

    Returns:
        List of dicts with keys: text (rewritten bullet),
        original_bullet_index (int), keywords_matched (List[str]).
    """
    # TODO: Use LLM with strict instruction: "Do NOT invent any facts."
    # TODO: Reorder: most relevant bullets first per JD requirements
    # TODO: Quantify: rewrite to lead with action verbs + metrics where already present
    # TODO: Append audit trail: input->output mapping
    raise NotImplementedError("tailor_bullets() is a placeholder. #TODO: LLM bullet tailoring with audit trail")


def rank_skills_for_job(candidate_skills: List[str], job_requirements: Dict[str, Any]) -> List[str]:
    """Reorder the candidate's skills list with most-JD-relevant first.

    Args:
        candidate_skills: Candidate's full skills list.
        job_requirements: Structured JD requirements.

    Returns:
        Reordered (possibly truncated) skills list.
    """
    # TODO: Prioritize exact matches to required_skills, then nice-to-have
    # TODO: Use semantic similarity for near-matches
    raise NotImplementedError("rank_skills_for_job() is a placeholder. #TODO: skill re-ranking")


def generate_tailored_resume(
    profile: Dict[str, Any],
    job: Dict[str, Any],
    requirements: Dict[str, Any],
) -> Dict[str, Any]:
    """Full tailoring pipeline producing a tailored resume draft.

    Args:
        profile: Structured candidate profile.
        job: Target job record.
        requirements: Structured JD requirements.

    Returns:
        Dict with tailored sections: summary, reordered_experience (with
        tailored bullets), reordered_skills, plus an audit log.
    """
    # TODO: Optional: Generate a 2-line professional summary (no inventions)
    # TODO: Call tailor_bullets() per experience entry
    # TODO: Call rank_skills_for_job()
    # TODO: Compile + return structured resume dict with audit trail
    raise NotImplementedError("generate_tailored_resume() is a placeholder. #TODO: full tailoring pipeline")


def validate_no_inventions(
    tailored: Dict[str, Any],
    original_profile: Dict[str, Any],
) -> List[str]:
    """Post-validation step: ensure no fabricated content.

    Args:
        tailored: Output of generate_tailored_resume().
        original_profile: Original structured profile.

    Returns:
        List of warning strings. Empty list = OK.
    """
    # TODO: N-gram overlap check: every output sentence should mostly overlap with input
    # TODO: LLM-as-judge audit: "Does any bullet contain a fact not present in the original?"
    # TODO: Block generation if any fabrication is detected — never auto-accept
    raise NotImplementedError("validate_no_inventions() is a placeholder. #TODO: anti-fabrication validator")
