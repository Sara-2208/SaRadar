"""Job discovery via JSearch (Phase 4A): fetch, normalize, filter, dedupe, store.

Protects the free quota: every request is counted per month and the
search stops at job_search.monthly_budget.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests

from saradar import job_store
from saradar.config import get_api_key, load_preferences

logger = logging.getLogger("saradar.jobs")

PROVIDER = "jsearch"
DEFAULT_SEARCH = {
    "url": "https://jsearch.p.rapidapi.com/search",
    "host": "jsearch.p.rapidapi.com",
    "country": "my",
    "date_posted": "week",
    "monthly_budget": 180,
    "queries": ["AI engineer in Kuala Lumpur, Malaysia"],
}
DEFAULT_KEEP = ["ai", "data", "machine learning", "ml", "llm", "genai",
                "analytics", "analyst", "scientist", "automation"]
AREA_STATES = {"kuala lumpur", "federal territory of kuala lumpur",
               "wilayah persekutuan kuala lumpur", "selangor", "putrajaya",
               "federal territory of putrajaya"}
AREA_CITIES = {"kuala lumpur", "petaling jaya", "puchong", "cyberjaya", "shah alam",
               "subang jaya", "klang", "seri kembangan", "kajang", "bangi", "putrajaya",
               "damansara", "cheras", "ampang", "balakong", "sepang"}


class BudgetExceeded(RuntimeError):
    """Monthly JSearch budget reached, or RapidAPI returned 429."""


@dataclass
class JobPosting:
    hash: str
    title: str
    company: str
    url: Optional[str] = None
    source: str = PROVIDER
    publisher: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    work_mode: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    description: str = ""
    posted_at: Optional[str] = None
    employment_type: Optional[str] = None
    external_id: Optional[str] = None


@dataclass
class SearchReport:
    requests_used: int = 0
    fetched: int = 0
    kept: List[JobPosting] = field(default_factory=list)
    skipped: List[Tuple[str, str]] = field(default_factory=list)  # (title, reason)
    new: List[JobPosting] = field(default_factory=list)
    budget_left: int = 0
    messages: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------


def job_hash(title: str, company: str) -> str:
    key = f"{job_store.norm_title(company)}|{job_store.norm_title(title)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def normalize(raw: Dict[str, Any]) -> JobPosting:
    title = (raw.get("job_title") or "").strip()
    company = (raw.get("employer_name") or "").strip()
    if raw.get("job_is_remote"):
        mode = "Remote"
    elif "hybrid" in title.lower():
        mode = "Hybrid"
    else:
        mode = None
    return JobPosting(
        hash=job_hash(title, company),
        title=title,
        company=company,
        url=raw.get("job_apply_link"),
        publisher=raw.get("job_publisher"),
        city=raw.get("job_city"),
        state=raw.get("job_state"),
        country=raw.get("job_country"),
        work_mode=mode,
        lat=raw.get("job_latitude"),
        lng=raw.get("job_longitude"),
        description=(raw.get("job_description") or "").strip(),
        posted_at=raw.get("job_posted_at_datetime_utc"),
        employment_type=raw.get("job_employment_type"),
        external_id=raw.get("job_id"),
    )


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def _km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(word.lower())}(?![a-z0-9])", text) is not None


def in_area(job: JobPosting, prefs: Dict[str, Any]) -> bool:
    if job.work_mode == "Remote":
        return True
    state, city = (job.state or "").lower(), (job.city or "").lower()
    if state in AREA_STATES or city in AREA_CITIES:
        return True
    areas = [a.lower() for a in prefs.get("areas", [])]
    if any(a and (a in state or a in city) for a in areas):
        return True
    if job.lat is not None and job.lng is not None:
        home = (float(prefs.get("home_lat", 3.1390)), float(prefs.get("home_lng", 101.6869)))
        return _km(home[0], home[1], job.lat, job.lng) <= float(prefs.get("max_distance_km", 40))
    return False


def filter_reason(job: JobPosting, prefs: Dict[str, Any]) -> Optional[str]:
    """None = keep; otherwise the reason it was skipped."""
    title = job.title.lower()
    if not title or not job.company:
        return "missing title or company"
    for kw in prefs.get("skip_title_keywords", []):
        if _has_word(title, str(kw)):
            return f"title has '{kw}'"
    keep = prefs.get("keep_title_keywords") or DEFAULT_KEEP
    if not any(_has_word(title, str(k)) for k in keep):
        return "title not relevant"
    if not in_area(job, prefs):
        return f"outside area ({job.city or job.state or 'unknown'})"
    return None


def dedupe(jobs: List[JobPosting]) -> List[JobPosting]:
    """Merge near-duplicates in one batch; keep the longest description."""
    out: List[JobPosting] = []
    for j in jobs:
        twin = next((o for o in out if o.company.lower() == j.company.lower()
                     and job_store.similar_title(o.title, j.title)), None)
        if twin is None:
            out.append(j)
        elif len(j.description) > len(twin.description):
            out[out.index(twin)] = j
    return out


# ---------------------------------------------------------------------------
# JSearch call
# ---------------------------------------------------------------------------


def _search(query: str, cfg: Dict[str, Any], api_key: str) -> List[Dict[str, Any]]:
    params = {
        "query": query, "page": 1, "num_pages": 1,
        "country": cfg["country"], "date_posted": cfg["date_posted"],
        "employment_types": "FULLTIME",
    }
    headers = {"x-rapidapi-key": api_key, "x-rapidapi-host": cfg["host"]}
    resp = requests.get(cfg["url"], headers=headers, params=params, timeout=30)
    if resp.status_code == 429:
        raise BudgetExceeded("RapidAPI quota or rate limit reached (429)")
    if resp.status_code == 404:
        raise RuntimeError(f"JSearch URL not found (404): {cfg['url']}. "
                           "Check job_search.url in preferences.yaml")
    resp.raise_for_status()
    data = resp.json().get("data")
    if isinstance(data, dict):
        return data.get("jobs") or []
    return data if isinstance(data, list) else []


def run_search(
    preferences: Optional[Dict[str, Any]] = None,
    max_queries: Optional[int] = None,
    dry_run: bool = False,
    db_path: Optional[str] = None,
) -> SearchReport:
    """Run the configured queries, filter + dedupe, store, return a report."""
    prefs = preferences if preferences is not None else load_preferences()
    cfg = {**DEFAULT_SEARCH, **(prefs.get("job_search") or {})}
    queries = list(cfg["queries"])[: max_queries or None]
    report = SearchReport()

    used = job_store.get_usage(PROVIDER, db_path=db_path)
    budget = int(cfg["monthly_budget"])
    report.budget_left = max(0, budget - used)

    if dry_run:
        report.messages.append(f"Dry run: {len(queries)} queries, {report.budget_left} requests left this month")
        return report

    api_key = get_api_key("RAPIDAPI_KEY")
    if not api_key:
        raise RuntimeError("RAPIDAPI_KEY missing in .env")

    collected: List[JobPosting] = []
    for q in queries:
        if used >= budget:
            report.messages.append(f"Monthly budget reached ({budget}); skipped remaining queries")
            break
        raws = _search(q, cfg, api_key)
        used += 1
        report.requests_used += 1
        job_store.add_usage(PROVIDER, db_path=db_path)
        report.fetched += len(raws)
        for raw in raws:
            job = normalize(raw)
            reason = filter_reason(job, prefs)
            if reason:
                report.skipped.append((job.title, reason))
            else:
                collected.append(job)

    report.kept = dedupe(collected)
    report.new = job_store.upsert_jobs(report.kept, db_path=db_path)
    report.budget_left = max(0, budget - used)
    return report