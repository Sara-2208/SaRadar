"""Daily loop: search -> score -> notify -> mark notified."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from saradar import job_store
from saradar.config import load_preferences
from saradar.jobs import BudgetExceeded, SearchReport, run_search
from saradar.notify import build_digest, empty_message, send_telegram
from saradar.pipeline import score_unscored

logger = logging.getLogger("saradar.daily")

DEFAULT_NOTIFY = {"min_fit": 50, "max_jobs": 0, "show_stretch_count": True,
                  "send_when_empty": False}


@dataclass
class DailyReport:
    search: Optional[SearchReport] = None
    scored: int = 0
    failed: int = 0
    candidates: int = 0
    notified: int = 0
    messages: List[str] = field(default_factory=list)
    sent: int = 0
    errors: List[str] = field(default_factory=list)


def run_daily(
    do_search: bool = True,
    dry_run: bool = False,
    preferences: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> DailyReport:
    prefs = preferences if preferences is not None else load_preferences()
    ncfg = {**DEFAULT_NOTIFY, **(prefs.get("notify") or {})}
    rep = DailyReport()

    if do_search:
        try:
            rep.search = run_search(preferences=prefs, db_path=db_path)
        except BudgetExceeded as e:
            rep.errors.append(f"Job search stopped: {e}")
        except Exception as e:  # noqa: BLE001
            rep.errors.append(f"Job search failed: {e}")

    sr = score_unscored(limit=50, preferences=prefs, db_path=db_path)
    if sr.no_profile:
        rep.errors.append("No saved profile, jobs not scored")
    rep.scored, rep.failed = len(sr.scored), len(sr.failed)

    jobs = job_store.unnotified_scored(db_path=db_path)
    rep.candidates = len(jobs)
    rep.messages = build_digest(jobs, min_fit=int(ncfg["min_fit"]),
                                max_jobs=int(ncfg["max_jobs"]),
                                show_stretch_count=bool(ncfg["show_stretch_count"]))
    if not rep.messages and ncfg["send_when_empty"]:
        rep.messages = [empty_message()]
    if rep.errors:
        rep.messages.append("⚠️ SaRadar: " + " | ".join(rep.errors))

    if dry_run:
        return rep

    for msg in rep.messages:
        send_telegram(msg)
        rep.sent += 1
    if jobs:
        job_store.mark_notified([j["hash"] for j in jobs], db_path=db_path)
        rep.notified = len(jobs)
    return rep