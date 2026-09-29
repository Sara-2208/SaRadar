"""End-to-end test for saradar.llm against real API keys.

Run from the project root (or anywhere — sys.path is fixed up below):

    python scripts/test_llm.py
"""

import os
import sys
from pathlib import Path

# Ensure `from saradar import llm` works even when run as scripts/test_llm.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
from saradar import llm  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")


def run(label: str, fn):
    """Execute ``fn``, print LLMResult details or the exception."""
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    try:
        result = fn()
    except llm.AllModelsFailed as e:
        print(f"❌ All models failed. {len(e.attempts)} attempts:")
        for a in e.attempts:
            print(f"   ✗ {a.model_spec}: {a.reason}")
        return
    print(f"Model used : {result.model_used}")
    if result.attempts:
        print(f"Fallbacks  : {len(result.attempts)}")
        for a in result.attempts:
            print(f"   ✗ {a.model_spec}: {a.reason}")
    else:
        print("Fallbacks  : (none)")
    text = (result.text or "").strip()
    preview = text if len(text) < 600 else text[:600] + "\n... [truncated]"
    print(f"Output:\n{preview}")


# ---------------------------------------------------------------------------
# 1. Fast tier — plain text
# ---------------------------------------------------------------------------
run(
    "Fast tier (plain text)",
    lambda: llm.complete("Say exactly: 'Hello from SaRadar fast tier!'"),
)

# ---------------------------------------------------------------------------
# 2. Smart tier — plain text (single sentence reasoning)
# ---------------------------------------------------------------------------
run(
    "Smart tier (plain text)",
    lambda: llm.complete(
        "In one sentence, what is retrieval-augmented generation?",
        tier="smart",
    ),
)

# ---------------------------------------------------------------------------
# 3. Fast tier — JSON mode
#    Prompt explicitly contains "JSON" per Groq requirements.
# ---------------------------------------------------------------------------
run(
    "Fast tier (json_mode)",
    lambda: llm.complete(
        'Return this as JSON: {"status":"ok","count":3}',
        json_mode=True,
    ),
)

# ---------------------------------------------------------------------------
# 4. Bonus: complete_json() variant returning a parsed dict
# ---------------------------------------------------------------------------
print(f"\n{'=' * 60}")
print("  Fast tier (complete_json -> parsed dict)")
print(f"{'=' * 60}")
try:
    data, result = llm.complete_json(
        "Return a JSON object with keys: color (3 hex strings), shape (3 types)"
    )
    print(f"Model used : {result.model_used}")
    print(f"Parsed dict: {data}")
except llm.AllModelsFailed as e:
    print(f"❌ All models failed. {len(e.attempts)} attempts")
    for a in e.attempts:
        print(f"   ✗ {a.model_spec}: {a.reason}")
