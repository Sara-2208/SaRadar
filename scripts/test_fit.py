"""Score your saved profile against a JD file.

Usage:
    python scripts/test_fit.py data/sample_jd.txt
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from saradar import db  # noqa: E402
from saradar.requirements_extractor import extract_requirements  # noqa: E402
from saradar.scorer import explain_fit, score_fit  # noqa: E402

if len(sys.argv) < 2:
    print("Usage: python scripts/test_fit.py path/to/jd.txt")
    sys.exit(1)

profile = db.load_profile()
if not profile:
    print("No saved profile. Save it on the Profile page first.")
    sys.exit(1)

jd = Path(sys.argv[1]).read_text(encoding="utf-8")
req, _ = extract_requirements(jd)
print("Scoring (first run downloads the embedding model, ~90 MB)...")
fit = score_fit(profile, req, jd_text=jd)

icons = {"exact": "✅", "similar": "🟢", "partial": "🟡", "missing": "❌"}
print(f"\nFIT: {fit.score}% ({fit.label}), confidence: {fit.confidence}")
print("\nBreakdown:")
for k, v in fit.breakdown.items():
    print(f"  {k:13}: {v}")

for title, items in (("Must-have", fit.must_have), ("Nice-to-have", fit.nice_to_have)):
    print(f"\n{title}:")
    for m in items or []:
        sim = f", sim {m.similarity}" if m.similarity is not None else ""
        ev = f"  <- {m.evidence[:70]}" if m.evidence else ""
        print(f"  {icons[m.kind]} {m.requirement} ({m.kind}{sim}){ev}")
    if not items:
        print("  (none listed)")

if fit.notes:
    print("\nNotes:")
    for n in fit.notes:
        print(f"  - {n}")

print("\nWhy:")
print(explain_fit(fit, req))