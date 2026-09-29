"""Fit scoring engine.

Combines multiple signals (skill overlap, experience match, location match,
education match, seniority match) into a single 0-100 fit score, plus a
human-readable explanation.
"""

from typing import Any, Dict, Tuple

# TODO: Make scoring weights configurable via preferences.yaml
# TODO: Allow per-user calibration (e.g. user cares less about degree match)
# TODO: Store explainability traces alongside scores for transparency


def compute_fit_score(
    profile: Dict[str, Any],
    job: Dict[str, Any],
    requirements: Dict[str, Any],
) -> Tuple[int, Dict[str, Any], str]:
    """Compute overall fit score and explanation for a (profile, job) pair.

    Args:
        profile: Structured candidate profile (skills, experience, etc.).
        job: Raw job record (title, company, location, description, etc.).
        requirements: Structured requirements extracted from the JD.

    Returns:
        Tuple of:
        - score (int): 0-100 overall fit score.
        - breakdown (dict): Per-signal scores (skills, experience, location, ...).
        - explanation (str): Human-readable 2-3 sentence fit summary.
    """
    # TODO: 1. Skill overlap score (required + nice-to-have weighted)
    # TODO: 2. Years-of-experience match (penalize under/over significantly)
    # TODO: 3. Location / distance / work-mode match (use max_distance_km)
    # TODO: 4. Education level match
    # TODO: 5. Seniority / title-level match (avoid head/director/principal via skip list)
    # TODO: 6. Weighted linear combination -> int score
    # TODO: 7. LLM-generated human explanation (NEVER invent experience)
    raise NotImplementedError("compute_fit_score() is a placeholder. #TODO: multi-signal scoring pipeline")


def passes_filters(job: Dict[str, Any], preferences: Dict[str, Any]) -> Tuple[bool, str]:
    """Quick pre-filter to reject jobs that don't meet hard user constraints.

    Checks: title keywords (skip intern/trainee/head/director/principal),
    geographic area, max distance, work-mode preferences.

    Args:
        job: Job record dict.
        preferences: User preferences from config.

    Returns:
        (True, "") if passes; (False, reason_string) otherwise.
    """
    # TODO: Implement skip_title_keywords case-insensitive check
    # TODO: Implement geographic filter (KL/Selangor/Putrajaya + distance)
    # TODO: Haversine distance for lat/lng vs area centroids
    raise NotImplementedError("passes_filters() is a placeholder. #TODO: hard-constraint pre-filtering")


def should_alert(score: int, preferences: Dict[str, Any]) -> bool:
    """Decide whether a scored job warrants a Telegram alert.

    Args:
        score: 0-100 fit score.
        preferences: User preferences (fit_alert_threshold used).

    Returns:
        True if score >= threshold.
    """
    # TODO: Also consider is_new flag to avoid repeat alerts
    # TODO: Add a daily alert cap to prevent spam
    threshold = preferences.get("fit_alert_threshold", 70)
    # TODO: Replace stub with real logic + logging
    raise NotImplementedError("should_alert() is a placeholder. #TODO: threshold + dedupe logic")
