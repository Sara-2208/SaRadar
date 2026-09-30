"""Run the daily loop.

Usage:
    python scripts/daily_run.py --dry-run --no-search   # preview, no API, no Telegram
    python scripts/daily_run.py --no-search             # notify from saved jobs only
    python scripts/daily_run.py                         # full: search + score + notify
"""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
logging.getLogger("httpx").setLevel(logging.WARNING)

from saradar.daily import run_daily  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true", help="don't send or mark anything")
parser.add_argument("--no-search", action="store_true", help="skip JSearch (saves quota)")
args = parser.parse_args()

print(f"=== SaRadar daily run {datetime.now():%Y-%m-%d %H:%M} ===")
rep = run_daily(do_search=not args.no_search, dry_run=args.dry_run)

if rep.search:
    s = rep.search
    print(f"Search : {s.requests_used} requests, {s.fetched} fetched, "
          f"{len(s.new)} new, {s.budget_left} left this month")
print(f"Scored : {rep.scored} (failed {rep.failed})")
print(f"To notify: {rep.candidates} jobs -> {len(rep.messages)} message(s)")
for e in rep.errors:
    print(f"  ! {e}")
if args.dry_run:
    print("\n--- Preview (not sent) ---")
    for m in rep.messages:
        print(m, "\n")
else:
    print(f"Sent {rep.sent} message(s), marked {rep.notified} jobs as notified")