"""Profile storage (SQLite locally, Supabase Postgres when DATABASE_URL is set)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from saradar import storage
from saradar.schemas import Profile

_PROFILE_COLS = {
    "name": "TEXT", "email": "TEXT", "skills": "TEXT", "experience": "TEXT",
    "education": "TEXT", "raw_text": "TEXT", "profile_json": "TEXT", "updated_at": "TEXT",
}
_READY: set = set()


def init_db(db_path: Optional[str] = None) -> None:
    key = storage.target(db_path)
    if key in _READY:
        return
    with storage.connect(db_path) as conn:
        storage.ensure_table(conn, "profile", "id INTEGER PRIMARY KEY", _PROFILE_COLS)
    _READY.add(key)


def save_profile(profile: Profile, raw_text: Optional[str] = None,
                 db_path: Optional[str] = None) -> int:
    """Upsert the single profile row (id = 1). Keeps old raw_text if none given."""
    init_db(db_path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    values = (
        1, profile.name, profile.email, json.dumps(profile.all_skills()),
        json.dumps([e.model_dump() for e in profile.experience]),
        json.dumps([e.model_dump() for e in profile.education]),
        raw_text, profile.model_dump_json(), now,
    )
    with storage.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO profile (id, name, email, skills, experience, education, "
            "raw_text, profile_json, updated_at) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT (id) DO UPDATE SET name = excluded.name, email = excluded.email, "
            "skills = excluded.skills, experience = excluded.experience, "
            "education = excluded.education, "
            "raw_text = COALESCE(excluded.raw_text, profile.raw_text), "
            "profile_json = excluded.profile_json, updated_at = excluded.updated_at",
            values,
        )
    return 1


def load_profile(db_path: Optional[str] = None) -> Optional[Profile]:
    init_db(db_path)
    with storage.connect(db_path) as conn:
        row = conn.execute("SELECT profile_json FROM profile WHERE id = 1").fetchone()
    if not row or not row["profile_json"]:
        return None
    return Profile.model_validate_json(row["profile_json"])