"""Job + API usage storage (SQLite locally, Supabase Postgres in the cloud)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from saradar import storage

FULL_JD_CHARS = 600

_JOB_COLUMNS = {
    "title": "TEXT", "company": "TEXT", "url": "TEXT", "source": "TEXT",
    "city": "TEXT", "state": "TEXT", "country": "TEXT", "work_mode": "TEXT",
    "lat": "REAL", "lng": "REAL", "description": "TEXT", "fit": "REAL",
    "is_new": "INTEGER DEFAULT 1", "jd_status": "TEXT", "created_at": "TEXT",
    "publisher": "TEXT", "posted_at": "TEXT", "employment_type": "TEXT",
    "external_id": "TEXT", "requirements_json": "TEXT", "fit_json": "TEXT",
    "fit_label": "TEXT", "status": "TEXT DEFAULT 'new'", "updated_at": "TEXT",
    "notified_at": "TEXT",
}
_READY: set = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def connect(db_path: Optional[str] = None) -> storage.Conn:
    conn = storage.connect(db_path)
    key = storage.target(db_path)
    if key not in _READY:
        storage.ensure_table(conn, "jobs", "hash TEXT PRIMARY KEY", _JOB_COLUMNS)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS api_usage (provider TEXT, month TEXT, "
            "count INTEGER DEFAULT 0, PRIMARY KEY (provider, month))"
        )
        if conn.kind == "pg":
            conn.execute("ALTER TABLE api_usage ENABLE ROW LEVEL SECURITY")
        conn.commit()
        _READY.add(key)
    return conn


# ---------------------------------------------------------------------------
# Near-duplicate detection
# ---------------------------------------------------------------------------


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def similar_title(a: str, b: str) -> bool:
    a, b = norm_title(a), norm_title(b)
    if not a or not b:
        return False
    if a == b or a.startswith(b) or b.startswith(a):
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.85


def _find_similar(conn: storage.Conn, company: str, title: str):
    rows = conn.execute(
        "SELECT hash, title, description FROM jobs WHERE lower(company) = lower(?)",
        (company or "",),
    ).fetchall()
    return next((r for r in rows if similar_title(r["title"], title)), None)


def _jd_status(description: Optional[str]) -> str:
    return "full" if len(description or "") >= FULL_JD_CHARS else "partial"


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def upsert_jobs(jobs: List[Any], db_path: Optional[str] = None) -> List[Any]:
    """Insert new jobs; update existing ones if the description got longer.
    Returns only NEW jobs."""
    new = []
    with connect(db_path) as conn:
        for j in jobs:
            row = conn.execute("SELECT hash, description FROM jobs WHERE hash = ?", (j.hash,)).fetchone()
            row = row or _find_similar(conn, j.company, j.title)
            if row:
                if len(j.description or "") > len(row["description"] or ""):
                    conn.execute(
                        "UPDATE jobs SET description=?, url=?, publisher=?, jd_status=?, updated_at=? "
                        "WHERE hash=?",
                        (j.description, j.url, j.publisher, _jd_status(j.description), _now(), row["hash"]),
                    )
                continue
            conn.execute(
                "INSERT INTO jobs (hash, title, company, url, source, publisher, city, state, country, "
                "work_mode, lat, lng, description, posted_at, employment_type, external_id, "
                "is_new, jd_status, status, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,'new',?,?)",
                (j.hash, j.title, j.company, j.url, j.source, j.publisher, j.city, j.state,
                 j.country, j.work_mode, j.lat, j.lng, j.description, j.posted_at,
                 j.employment_type, j.external_id, _jd_status(j.description), _now(), _now()),
            )
            new.append(j)
    return new


def list_jobs(db_path: Optional[str] = None, only_new: bool = False, limit: int = 200) -> List[Dict[str, Any]]:
    where = "WHERE is_new = 1" if only_new else ""
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM jobs {where} ORDER BY (fit IS NULL), fit DESC, posted_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_job(job_hash: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE hash = ?", (job_hash,)).fetchone()
    return dict(row) if row else None


def mark_seen(job_hash: str, db_path: Optional[str] = None) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE jobs SET is_new = 0 WHERE hash = ?", (job_hash,))


def save_fit(job_hash: str, requirements_json: str, fit_json: str, fit: float,
             label: str, db_path: Optional[str] = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET requirements_json=?, fit_json=?, fit=?, fit_label=?, updated_at=? "
            "WHERE hash=?",
            (requirements_json, fit_json, fit, label, _now(), job_hash),
        )


# ---------------------------------------------------------------------------
# API usage (protects the free quota)
# ---------------------------------------------------------------------------


def get_usage(provider: str, month: Optional[str] = None, db_path: Optional[str] = None) -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT count FROM api_usage WHERE provider=? AND month=?",
            (provider, month or month_key()),
        ).fetchone()
    return int(row["count"]) if row else 0


def add_usage(provider: str, n: int = 1, month: Optional[str] = None, db_path: Optional[str] = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO api_usage (provider, month, count) VALUES (?, ?, ?) "
            "ON CONFLICT (provider, month) DO UPDATE SET count = api_usage.count + excluded.count",
            (provider, month or month_key(), n),
        )


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def unnotified_scored(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE fit IS NOT NULL AND notified_at IS NULL ORDER BY fit DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def mark_notified(hashes: List[str], db_path: Optional[str] = None) -> None:
    with connect(db_path) as conn:
        conn.executemany("UPDATE jobs SET notified_at = ? WHERE hash = ?",
                         [(_now(), h) for h in hashes])