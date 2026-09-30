"""Check that DATABASE_URL (Supabase) works."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

url = os.getenv("DATABASE_URL")
if not url:
    print("❌ DATABASE_URL missing in .env")
    sys.exit(1)

import psycopg  # noqa: E402

try:
    with psycopg.connect(url, connect_timeout=15) as conn:
        version = conn.execute("select version()").fetchone()[0]
    print("✅ Connected to Supabase!")
    print("  ", version[:60])
except Exception as e:
    print("❌ Connection failed:", e)