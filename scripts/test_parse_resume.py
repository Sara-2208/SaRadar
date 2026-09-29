"""Parse a resume PDF and print the structured profile (PII masked).

Usage:
    python scripts/test_parse_resume.py data/resume.pdf
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from saradar import resume_parser as rp  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_parse_resume.py path/to/resume.pdf")
        sys.exit(1)

    path = Path(sys.argv[1])
    print(f"=== Parsing {path.name} ===")
    text = rp.extract_text(path)
    print(f"Extracted text length : {len(text)} chars")

    outcome = rp.parse_resume_full(text)
    print(f"Models used           : {', '.join(outcome.models_used)}")
    for r in outcome.results:
        for a in r.attempts:
            print(f"  fallback: {a.model_spec}: {a.reason}")

    print("\n=== Profile JSON (PII masked) ===")
    print(json.dumps(outcome.profile.masked_dump(), indent=2, ensure_ascii=False))

    p = outcome.profile
    print("\n=== Section counts ===")
    for name in ["experience", "education", "projects", "activities", "certifications", "languages"]:
        print(f"{name:15}: {len(getattr(p, name))}")
    print(f"{'skills':15}: {len(p.all_skills())}")

    print("\n=== Warnings ===")
    print("\n".join(f"  ! {w}" for w in outcome.warnings) or "  none")


if __name__ == "__main__":
    main()