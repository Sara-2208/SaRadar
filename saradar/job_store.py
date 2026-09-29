"""SQLite storage for jobs + API usage (Phase 4A).

Uses the same database as the profile: data/saradar.db
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "saradar.db"
FULL_JD_CHARS = 600

_JOB_COLUMNS = {
    "title": "TEXT", "company": "TEXT", "url": "TEXT", "source": "TEXT",
    "city": "TEXT", "state": "TEXT", "country": "TEXT", "work_mode": "TEXT",
    "lat": "REAL", "lng": "REAL", "description": "TEXT", "fit": "REAL",
    "is_new": "INTEGER DEFAULT 1", "jd_status": "TEXT", "created_at": "TEXT",
    "publisher": "TEXT", "posted_at": "TEXT", "employment_type": "TEXT",
    "external_id": "TEXT", "requirements_json": "TEXT", "fit_json": "TEXT",
    "fit_label": "TEXT", "status": "TEXT DEFAULT 'new'", "updated_at": "TEXT",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    cols = ", ".join(f"{name} {kind}" for name, kind in _JOB_COLUMNS.items())
    conn.execute(f"CREATE TABLE IF NOT EXISTS jobs (hash TEXT PRIMARY KEY, {cols})")
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    for name, kind in _JOB_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {kind}")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_usage ("
        "provider TEXT, month TEXT, count INTEGER DEFAULT 0, "
        "PRIMARY KEY (provider, month))"
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Near-duplicate detection
# ---------------------------------------------------------------------------


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def similar_title(a: str, b: str) -> bool:
    """'AI Engineer: GenAI, ML' ~ 'AI Engineer: GenAI, ML & Cloud Solutions'."""
    a, b = norm_title(a), norm_title(b)
    if not a or not b:
        return False
    if a == b or a.startswith(b) or b.startswith(a):
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.85


def _find_similar(conn: sqlite3.Connection, company: str, title: str) -> Optional[sqlite3.Row]:
    rows = conn.execute(
        "SELECT hash, title, description FROM jobs WHERE lower(company) = lower(?)",
        (company or "",),
    ).fetchall()
    return next((r for r in rows if similar_title(r["title"], title)), None)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def upsert_jobs(jobs: List[Any], db_path: Optional[str] = None) -> List[Any]:
    """Insert new jobs; update existing ones if we got a longer description.

    Returns only the jobs that are NEW (never seen before).
    """
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


def _jd_status(description: Optional[str]) -> str:
    return "full" if len(description or "") >= FULL_JD_CHARS else "partial"


def list_jobs(db_path: Optional[str] = None, only_new: bool = False, limit: int = 200) -> List[Dict[str, Any]]:
    where = "WHERE is_new = 1" if only_new else ""
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM jobs {where} "
            "ORDER BY (fit IS NULL), fit DESC, posted_at DESC LIMIT ?",
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
            "ON CONFLICT(provider, month) DO UPDATE SET count = count + excluded.count",
            (provider, month or month_key(), n),
        )