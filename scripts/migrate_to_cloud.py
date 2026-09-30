"""Copy local data/saradar.db (profile, jobs, api_usage) to Supabase."""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from saradar import db, job_store, storage  # noqa: E402
from saradar.schemas import Profile  # noqa: E402

if not storage.database_url():
    print("❌ DATABASE_URL missing in .env")
    sys.exit(1)
if not storage.DEFAULT_SQLITE.exists():
    print("❌ No local data/saradar.db found")
    sys.exit(1)

src = sqlite3.connect(str(storage.DEFAULT_SQLITE))
src.row_factory = sqlite3.Row

# 1. Profile
row = src.execute("SELECT * FROM profile WHERE id = 1").fetchone()
if row and row["profile_json"]:
    db.save_profile(Profile.model_validate_json(row["profile_json"]), raw_text=row["raw_text"])
    print("✅ Profile copied")
else:
    print("⚠️ No local profile to copy")

# 2. Jobs + usage
with job_store.connect() as dst:
    cloud_cols = storage.columns(dst, "jobs")
    jobs = src.execute("SELECT * FROM jobs").fetchall()
    copied = 0
    for r in jobs:
        cols = [c for c in r.keys() if c in cloud_cols]
        placeholders = ",".join("?" for _ in cols)
        dst.execute(
            f"INSERT INTO jobs ({','.join(cols)}) VALUES ({placeholders}) ON CONFLICT (hash) DO NOTHING",
            [r[c] for c in cols],
        )
        copied += 1
    print(f"✅ Jobs copied: {copied}")

    try:
        for u in src.execute("SELECT * FROM api_usage").fetchall():
            dst.execute(
                "INSERT INTO api_usage (provider, month, count) VALUES (?, ?, ?) "
                "ON CONFLICT (provider, month) DO UPDATE SET count = excluded.count",
                (u["provider"], u["month"], u["count"]),
            )
        print("✅ API usage copied")
    except sqlite3.OperationalError:
        print("⚠️ No local api_usage table")

src.close()
print("\nDone. SaRadar now reads/writes Supabase while DATABASE_URL is set.")