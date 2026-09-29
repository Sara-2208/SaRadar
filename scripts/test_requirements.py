"""Extract requirements from a JD text file.

Usage:
    python scripts/test_requirements.py data/sample_jd.txt
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from saradar.requirements_extractor import extract_requirements  # noqa: E402

if len(sys.argv) < 2:
    print("Usage: python scripts/test_requirements.py path/to/jd.txt")
    sys.exit(1)

jd = Path(sys.argv[1]).read_text(encoding="utf-8")
req, result = extract_requirements(jd)
print(f"Model used : {result.model_used}")
print(f"JD length  : {len(jd)} chars ({req.jd_quality})\n")
print(json.dumps(req.model_dump(), indent=2, ensure_ascii=False))