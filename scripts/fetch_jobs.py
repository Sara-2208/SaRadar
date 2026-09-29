"""Fetch jobs from JSearch and store them.

Usage:
    python scripts/fetch_jobs.py --dry-run          # no API call, shows budget
    python scripts/fetch_jobs.py --max-queries 1    # uses 1 request
    python scripts/fetch_jobs.py                    # all queries
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from saradar.jobs import run_search  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--max-queries", type=int, default=None)
args = parser.parse_args()

rep = run_search(max_queries=args.max_queries, dry_run=args.dry_run)

for m in rep.messages:
    print(f"ℹ {m}")
print(f"Requests used : {rep.requests_used}   (left this month: {rep.budget_left})")
print(f"Fetched       : {rep.fetched}")
print(f"Kept          : {len(rep.kept)}")
print(f"NEW           : {len(rep.new)}")

if rep.new:
    print("\n=== New jobs ===")
    for j in rep.new:
        where = j.city or j.state or "?"
        print(f"  • {j.title} | {j.company} | {where} | via {j.publisher}")

if rep.skipped:
    print("\n=== Skipped ===")
    for title, reason in rep.skipped:
        print(f"  - {title}  ({reason})")