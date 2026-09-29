"""SQLite database operations.

All persistence logic lives here. DB file lives at ``data/saradar.db``.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

# TODO: Use a connection pool / thread-local connection for multi-threaded API use
# TODO: Wrap all writes in transactions with proper rollback
# TODO: Add schema migration support (schema version table + migration scripts)
# TODO: Add indices on frequently queried columns (jobs.fit, jobs.created_at, etc.)


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "saradar.db"


@contextmanager
def get_connection(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Context manager yielding a SQLite connection with row factory enabled.

    Usage::

        with get_connection() as conn:
            row = conn.execute("SELECT ...").fetchone()

    Args:
        db_path: Override path to .db file (default: data/saradar.db).

    Yields:
        sqlite3.Connection with ``row_factory = sqlite3.Row`` and
        ``foreign_keys = ON``.
    """
    # TODO: Ensure WAL mode for better concurrent read performance
    # TODO: Ensure the parent data/ directory exists
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(schema_path: str | Path | None = None, db_path: str | Path | None = None) -> None:
    """Initialize the database by executing schema.sql.

    Safe to call on an existing DB (tables use IF NOT EXISTS).

    Args:
        schema_path: Path to db/schema.sql. Defaults to project location.
        db_path: Override DB path.
    """
    # TODO: Add a schema_version table and migration framework
    if schema_path is None:
        schema_path = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    with get_connection(db_path) as conn:
        conn.executescript(schema_sql)


# ---------- Profile ----------

def upsert_profile(profile: Dict[str, Any], db_path: str | Path | None = None) -> int:
    """Insert or update the user profile (single-row table).

    Args:
        profile: Dict with keys: name, email, skills (JSON str),
            experience (JSON str), education (JSON str), raw_text.

    Returns:
        The profile row id (always 1 for single-row pattern).
    """
    # TODO: id=1 convention (single user app)
    # TODO: Set updated_at to current UTC timestamp
    raise NotImplementedError("upsert_profile() is a placeholder. #TODO: profile upsert SQL")


def get_profile(db_path: str | Path | None = None) -> Optional[Dict[str, Any]]:
    """Fetch the user profile.

    Returns:
        Profile dict or None if not set.
    """
    # TODO: SELECT * FROM profile WHERE id = 1
    raise NotImplementedError("get_profile() is a placeholder. #TODO: get profile by id=1")


# ---------- Jobs ----------

def upsert_job(job: Dict[str, Any], db_path: str | Path | None = None) -> str:
    """Insert a job, or update it if hash already exists.

    Args:
        job: Dict matching the jobs table schema.

    Returns:
        The job hash (primary key).
    """
    # TODO: Use INSERT OR REPLACE (ON CONFLICT for SQLite 3.24+)
    raise NotImplementedError("upsert_job() is a placeholder. #TODO: job upsert by hash")


def bulk_upsert_jobs(jobs: List[Dict[str, Any]], db_path: str | Path | None = None) -> int:
    """Bulk upsert a list of jobs in a single transaction.

    Args:
        jobs: List of job dicts.

    Returns:
        Number of rows affected.
    """
    # TODO: Executemany pattern for speed
    raise NotImplementedError("bulk_upsert_jobs() is a placeholder. #TODO: batch job upsert")


def get_jobs(
    limit: int = 100,
    offset: int = 0,
    min_fit: int | None = None,
    is_new_only: bool = False,
    db_path: str | Path | None = None,
) -> List[Dict[str, Any]]:
    """Query jobs with optional filters, ordered by fit desc, created_at desc.

    Args:
        limit: Max rows.
        offset: Pagination offset.
        min_fit: If set, only return jobs with fit >= min_fit.
        is_new_only: Only return jobs marked is_new=1.

    Returns:
        List of job dicts.
    """
    # TODO: Build WHERE clause dynamically
    raise NotImplementedError("get_jobs() is a placeholder. #TODO: paginated filtered job query")


def get_job_by_hash(job_hash: str, db_path: str | Path | None = None) -> Optional[Dict[str, Any]]:
    """Fetch a single job by its hash.

    Args:
        job_hash: The jobs.hash primary key value.

    Returns:
        Job dict or None.
    """
    # TODO: Simple single-row SELECT
    raise NotImplementedError("get_job_by_hash() is a placeholder.")


def mark_job_fit(job_hash: str, fit: int, jd_status: str = "scored", db_path: str | Path | None = None) -> None:
    """Update the fit score and JD processing status of a job.

    Args:
        job_hash: Job PK.
        fit: 0-100 integer score.
        jd_status: e.g. "pending", "parsed", "scored", "failed".
    """
    raise NotImplementedError("mark_job_fit() is a placeholder. #TODO: UPDATE jobs SET fit=?, jd_status=?")


def mark_job_seen(job_hash: str, db_path: str | Path | None = None) -> None:
    """Mark a job as no longer new (is_new = 0)."""
    raise NotImplementedError("mark_job_seen() is a placeholder. #TODO: UPDATE is_new=0")


# ---------- Applications ----------

def create_application(
    job_hash: str,
    status: str = "applied",
    applied_date: str | None = None,
    notes: str = "",
    db_path: str | Path | None = None,
) -> int:
    """Insert a new application tracking row.

    Args:
        job_hash: References jobs(hash).
        status: "saved" | "applied" | "interview" | "offer" | "rejected".
        applied_date: ISO date string, defaults to today UTC.
        notes: Free-text user notes.

    Returns:
        New application id (auto-increment PK).
    """
    # TODO: Set created_at = utcnow
    # TODO: Foreign key constraint enforced via PRAGMA foreign_keys
    raise NotImplementedError("create_application() is a placeholder. #TODO: INSERT applications")


def get_applications(
    job_hash: str | None = None,
    db_path: str | Path | None = None,
) -> List[Dict[str, Any]]:
    """List applications, optionally filtered to a specific job.

    Joins with jobs table to include title/company for convenience.
    """
    # TODO: SELECT a.*, j.title, j.company FROM applications a JOIN jobs j ON a.job_id = j.hash
    raise NotImplementedError("get_applications() is a placeholder. #TODO: applications query with join")


def update_application_status(
    application_id: int,
    status: str,
    notes: str | None = None,
    db_path: str | Path | None = None,
) -> None:
    """Update the status (and optionally notes) of an existing application."""
    raise NotImplementedError("update_application_status() is a placeholder. #TODO: UPDATE applications")
