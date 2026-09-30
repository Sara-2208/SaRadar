"""Database connection helper.

- DATABASE_URL set (Supabase)  -> Postgres
- otherwise, or db_path given  -> SQLite (local file / tests)

Code everywhere uses '?' placeholders; they're converted for Postgres.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Set

import saradar.config  # noqa: F401  (loads .env)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE = ROOT / "data" / "saradar.db"


def database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL") or None


def target(db_path: Optional[str] = None) -> str:
    if db_path:
        return f"sqlite:{db_path}"
    return "postgres" if database_url() else f"sqlite:{DEFAULT_SQLITE}"


class Conn:
    """Tiny wrapper so SQLite and Postgres look the same to our code."""

    def __init__(self, raw: Any, kind: str):
        self.raw, self.kind = raw, kind

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.kind == "pg" else sql

    def execute(self, sql: str, params: Sequence[Any] = ()):
        return self.raw.execute(self._sql(sql), params)

    def executemany(self, sql: str, seq: Iterable[Sequence[Any]]) -> None:
        if self.kind == "pg":
            with self.raw.cursor() as cur:
                cur.executemany(self._sql(sql), list(seq))
        else:
            self.raw.executemany(sql, list(seq))

    def commit(self) -> None:
        self.raw.commit()

    def __enter__(self) -> "Conn":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type:
                self.raw.rollback()
            else:
                self.raw.commit()
        finally:
            self.raw.close()


def connect(db_path: Optional[str] = None) -> Conn:
    url = database_url()
    if db_path or not url:
        path = Path(db_path) if db_path else DEFAULT_SQLITE
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(str(path))
        raw.row_factory = sqlite3.Row
        return Conn(raw, "sqlite")

    import psycopg
    from psycopg.rows import dict_row

    raw = psycopg.connect(url, row_factory=dict_row, connect_timeout=15, prepare_threshold=None)
    return Conn(raw, "pg")


def columns(conn: Conn, table: str) -> Set[str]:
    if conn.kind == "pg":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = ?", (table,)
        ).fetchall()
        return {r["column_name"] for r in rows}
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_table(conn: Conn, table: str, key_sql: str, cols: Dict[str, str]) -> None:
    """Create table if missing, add any missing columns, lock down on Postgres."""
    body = ", ".join([key_sql] + [f"{n} {t}" for n, t in cols.items()])
    conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({body})")
    existing = columns(conn, table)
    for name, kind in cols.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
    if conn.kind == "pg":
        conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")