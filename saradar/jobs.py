"""Job sourcing module.

Sources jobs ONLY from official APIs (e.g. via RapidAPI) and Gmail job
alerts. NO scraping of LinkedIn or JobStreet per project rules.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

# TODO: Implement RapidAPI job sources (e.g. JSearch, etc.)
# TODO: Implement Gmail job alert ingestion (via Gmail API, not scraping)
# TODO: Deduplicate jobs by content hash before insert
# TODO: Standardize fields across different sources into the jobs table schema


def compute_job_hash(job: Dict[str, Any]) -> str:
    """Compute a stable content hash for deduplication.

    Hash is based on a canonicalized combination of: title (lowercased),
    company (lowercased), city/state, and description snippet.

    Args:
        job: Job dict with at least title, company, location fields.

    Returns:
        Hex digest string suitable as the jobs.hash primary key.
    """
    # TODO: Use SHA-256 over a canonical JSON string
    # TODO: Normalize whitespace, case, and punctuation before hashing
    raise NotImplementedError("compute_job_hash() is a placeholder. #TODO: stable dedupe hash")


def geocode_location(city: str, state: str, country: str = "Malaysia") -> Optional[Dict[str, float]]:
    """Resolve a location to lat/lng coordinates for distance filtering.

    Args:
        city: City name.
        state: State/region name.
        country: Country name (default Malaysia).

    Returns:
        Dict with keys "lat" and "lng", or None if resolution fails.
    """
    # TODO: Use a free/official geocoding API
    # TODO: Cache results in a small lookup table to reduce API calls
    raise NotImplementedError("geocode_location() is a placeholder. #TODO: geocoding with cache")


def detect_work_mode(description: str, title: str = "") -> str:
    """Detect work mode from JD text and title.

    Args:
        description: Job description text.
        title: Job title (optional, extra context).

    Returns:
        "remote" | "hybrid" | "onsite" | "unknown".
    """
    # TODO: Keyword + LLM-based classification
    # TODO: Standardize values to match the jobs.work_mode column
    raise NotImplementedError("detect_work_mode() is a placeholder. #TODO: work-mode classification")


def fetch_from_rapidapi(preferences: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fetch jobs from RapidAPI job endpoints.

    Uses preferences (roles, areas) to build search queries.

    Args:
        preferences: User preferences dict.

    Returns:
        List of raw job dicts from the API (to be normalized later).
    """
    # TODO: Paginate through results
    # TODO: Respect rate limits (RapidAPI often has quota)
    # TODO: Never scrape LinkedIn/JobStreet — use only official API endpoints
    raise NotImplementedError("fetch_from_rapidapi() is a placeholder. #TODO: RapidAPI job ingestion")


def fetch_from_gmail_alerts(preferences: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse jobs received via Gmail job alert emails.

    Args:
        preferences: User preferences dict.

    Returns:
        List of normalized job dicts parsed from email bodies.
    """
    # TODO: Authenticate via Gmail OAuth — no password-based access
    # TODO: Search for job-alert emails with user-configurable subjects/senders
    # TODO: Extract job links, titles, companies, and follow link for full JD via official API only
    raise NotImplementedError("fetch_from_gmail_alerts() is a placeholder. #TODO: Gmail job alert ingestion")


def normalize_job(raw_job: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Normalize a raw job record into the jobs table schema.

    Args:
        raw_job: Source-specific job dict.
        source: Source identifier string (e.g. "rapidapi-js", "gmail-alert").

    Returns:
        Job dict matching the columns in db/schema.sql (jobs table),
        ready for upsert.
    """
    # TODO: Map source-specific fields to canonical schema
    # TODO: Compute hash, detect work_mode, geocode, set is_new=True, jd_status="pending"
    # TODO: created_at = utcnow ISO
    raise NotImplementedError("normalize_job() is a placeholder. #TODO: source->schema normalization")
