"""Score stored jobs and print the ranking.

Usage:
    python scripts/score_jobs.py              # score unscored jobs (max 20)
    python scripts/score_jobs.py --rescore    # re-score everything
"""
import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
logging.getLogger("httpx").setLevel(logging.WARNING)

from saradar import job_store  # noqa: E402
from saradar.pipeline import score_unscored  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--limit", type=int, default=20)
parser.add_argument("--rescore", action="store_true")
args = parser.parse_args()

print("Scoring jobs (first run loads the matching model)...")
rep = score_unscored(limit=args.limit, rescore=args.rescore)
if rep.no_profile:
    print("❌ No saved profile. Save it on the Profile page first.")
    sys.exit(1)

print(f"Scored: {len(rep.scored)}   Failed: {len(rep.failed)}")
for title, err in rep.failed:
    print(f"  ❌ {title}: {err[:120]}")

print("\n=== Ranking ===")
for j in job_store.list_jobs():
    score = "  -" if j["fit"] is None else f"{int(j['fit']):3d}"
    new = "🆕" if j["is_new"] else "  "
    print(f"{new} {score}%  {j['fit_label'] or '':10}  {j['title'][:55]} | {j['company'][:25]}")