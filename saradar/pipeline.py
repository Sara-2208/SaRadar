"""Score stored jobs (Phase 4B): requirements + fit for every unscored job.

Explanations are NOT generated here (saves LLM quota); the Jobs page
creates them on demand when you open a job.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from saradar import db as db_mod
from saradar import job_store
from saradar.requirements_extractor import extract_requirements
from saradar.schemas import JobRequirements, Profile
from saradar.scorer import FitResult, score_fit

logger = logging.getLogger("saradar.pipeline")


@dataclass
class ScoreReport:
    scored: List[Dict[str, Any]] = field(default_factory=list)
    failed: List[Tuple[str, str]] = field(default_factory=list)
    no_profile: bool = False


def _location(job: Dict[str, Any]) -> Optional[str]:
    return ", ".join(filter(None, [job.get("city"), job.get("state")])) or None


def score_job(
    job: Dict[str, Any],
    profile: Profile,
    preferences: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> Tuple[JobRequirements, FitResult]:
    """Extract requirements + score one stored job, and save the result."""
    text = job.get("description") or job.get("title") or ""
    req, _ = extract_requirements(
        text, title=job.get("title"), company=job.get("company"), location=_location(job)
    )
    if job.get("work_mode") and not req.work_mode:
        req = req.model_copy(update={"work_mode": job["work_mode"]})

    fit = score_fit(profile, req, jd_text=job.get("description"), preferences=preferences)
    job_store.save_fit(
        job["hash"], req.model_dump_json(), json.dumps(fit.to_dict()),
        fit.score, fit.label, db_path=db_path,
    )
    return req, fit


def score_unscored(
    limit: int = 20,
    rescore: bool = False,
    profile: Optional[Profile] = None,
    preferences: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> ScoreReport:
    """Score jobs that have no fit yet (or all, if rescore=True)."""
    report = ScoreReport()
    profile = profile or db_mod.load_profile()
    if not profile:
        report.no_profile = True
        return report

    jobs = [j for j in job_store.list_jobs(db_path=db_path, limit=500)
            if rescore or j.get("fit") is None][:limit]

    for job in jobs:
        try:
            _, fit = score_job(job, profile, preferences=preferences, db_path=db_path)
            report.scored.append({"title": job["title"], "company": job["company"],
                                  "score": fit.score, "label": fit.label})
        except Exception as exc:  # noqa: BLE001 (one bad job shouldn't stop the rest)
            logger.warning("Scoring failed for %s: %s", job.get("title"), exc)
            report.failed.append((job.get("title") or "?", str(exc)))
    return report