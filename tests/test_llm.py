"""Unit tests for saradar.llm — ALL mocked, no real API calls.

Targets:
- fallback order
- 429 cool-down skip
- timeout/5xx retry then next model
- 400 bad request → no retry, next model
- json_mode invalid-JSON retry on same model, then next
- missing API key → skip with clear reason
- all fail → AllModelsFailed exception with ordered attempts
- complete_json() → parsed dict
- SARADAR_FORCE_FAIL env hook
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from saradar import llm as llm_mod
from saradar.llm import (
    AllModelsFailed,
    FailedAttempt,
    LLMResult,
    _cooldown,
    _parse_model_spec,
)


# ---------------------------------------------------------------------------
# Minimal deterministic preferences (small 2-model tiers for fast tests)
# ---------------------------------------------------------------------------
MINI_PREFS = {
    "llm": {
        "fast": ["groq/g-fast", "gemini/g-fast"],
        "smart": ["groq/g-smart", "gemini/g-smart"],
        "timeout_seconds": 5,
        "max_retries": 1,
    }
}


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    """Reset cooldown, Gemini client, and API keys between tests."""
    _cooldown.clear()
    llm_mod._gemini_client = None
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gem")
    monkeypatch.delenv("SARADAR_FORCE_FAIL", raising=False)
    yield
    _cooldown.clear()
    llm_mod._gemini_client = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class ProviderSpy:
    """Injectable return/raise behaviour for _call_groq / _call_gemini.

    Usage::

        spy = ProviderSpy()
        spy.groq_returns = {"groq/g-fast": "hi"}
        spy.install(monkeypatch)
    """

    def __init__(self):
        self.groq_returns: dict[str, str] = {}
        self.gem_returns: dict[str, str] = {}
        self.groq_raises: dict[str, type[BaseException] | BaseException] = {}
        self.gem_raises: dict[str, type[BaseException] | BaseException] = {}
        self.groq_calls: list[tuple] = []
        self.gem_calls: list[tuple] = []

    def install(self, monkeypatch):
        def groq_fn(model_id, prompt, system, json_mode, timeout_seconds):
            self.groq_calls.append((model_id, prompt, system, json_mode, timeout_seconds))
            if model_id in self.groq_raises:
                err = self.groq_raises[model_id]
                raise err if not isinstance(err, type) else err()
            return self.groq_returns.get(model_id, "")

        def gem_fn(model_id, prompt, system, json_mode, timeout_seconds):
            self.gem_calls.append((model_id, prompt, system, json_mode, timeout_seconds))
            if model_id in self.gem_raises:
                err = self.gem_raises[model_id]
                raise err if not isinstance(err, type) else err()
            return self.gem_returns.get(model_id, "")

        monkeypatch.setattr(llm_mod, "_call_groq", groq_fn)
        monkeypatch.setattr(llm_mod, "_call_gemini", gem_fn)
        return self


# ---------------------------------------------------------------------------
# 1. parse_model_spec
# ---------------------------------------------------------------------------

def test_parse_model_spec_variants():
    assert _parse_model_spec("groq/openai/gpt-oss-20b") == ("groq", "openai/gpt-oss-20b")
    assert _parse_model_spec("gemini/gemini-3.5-flash-lite") == ("gemini", "gemini-3.5-flash-lite")
    with pytest.raises(ValueError):
        _parse_model_spec("no-slash-here")


# ---------------------------------------------------------------------------
# 2. Happy path: first model answers, no fallback
# ---------------------------------------------------------------------------

def test_complete_happy_path_first_model(monkeypatch):
    spy = ProviderSpy()
    spy.groq_returns["g-fast"] = "Hello fast"
    spy.install(monkeypatch)

    res = llm_mod.complete("Hi", tier="fast", preferences=MINI_PREFS)

    assert isinstance(res, LLMResult)
    assert res.text == "Hello fast"
    assert res.model_used == "groq/g-fast"
    assert res.attempts == []
    assert len(spy.groq_calls) == 1
    assert spy.gem_calls == []  # gemini never called


# ---------------------------------------------------------------------------
# 3. 429 on model 1 → fall back to model 2 + cooldown set + next call skips model 1
# ---------------------------------------------------------------------------

def test_fallback_on_429_and_cooldown(monkeypatch):
    spy = ProviderSpy()
    # Model 1 always 429
    spy.groq_raises["g-fast"] = RuntimeError("429 rate limit exceeded")
    spy.gem_returns["g-fast"] = "Gemini fast response"
    spy.install(monkeypatch)

    before = set(_cooldown.keys())

    # Call 1: groq 429 → gemini answers
    res = llm_mod.complete("Hi", tier="fast", preferences=MINI_PREFS)
    assert res.model_used == "gemini/g-fast"
    assert len(res.attempts) == 1
    assert res.attempts[0].model_spec == "groq/g-fast"
    assert "429" in res.attempts[0].reason.lower()
    assert "groq/g-fast" in _cooldown
    assert _cooldown["groq/g-fast"] > datetime.utcnow() + timedelta(minutes=59)

    # Call 2: groq still cooled → skip, go straight to gemini
    spy.groq_calls.clear()
    res2 = llm_mod.complete("Hi again", tier="fast", preferences=MINI_PREFS)
    assert res2.model_used == "gemini/g-fast"
    # The skip should be recorded in attempts even though it's pre-call
    specs = [a.model_spec for a in res2.attempts]
    assert "groq/g-fast" in specs
    assert "cooldown" in res2.attempts[specs.index("groq/g-fast")].reason.lower()
    # Crucially: _call_groq was NOT invoked (cooled before SDK)
    assert len(spy.groq_calls) == 0


# ---------------------------------------------------------------------------
# 4. timeout / 5xx → retry once → then next model
# ---------------------------------------------------------------------------

def test_timeout_retry_then_next_model(monkeypatch):
    spy = ProviderSpy()
    spy.groq_raises["g-fast"] = TimeoutError("request timed out")  # retried (max_retries=1 → 2 calls)
    spy.gem_returns["g-fast"] = "ok via gem"
    spy.install(monkeypatch)

    res = llm_mod.complete("Hi", tier="fast", preferences=MINI_PREFS)

    assert res.model_used == "gemini/g-fast"
    # groq was called 2 times (first try + 1 retry)
    assert len(spy.groq_calls) == 2
    specs = [a.model_spec for a in res.attempts]
    assert specs.count("groq/g-fast") == 1  # single FailedAttempt record (summarised)
    assert "timeout" in res.attempts[0].reason.lower()


# ---------------------------------------------------------------------------
# 5. 400 bad request → NO retry, next model immediately
# ---------------------------------------------------------------------------

def test_400_bad_request_no_retry_next_model(monkeypatch):
    spy = ProviderSpy()
    spy.groq_raises["g-fast"] = ValueError("400 bad request: invalid model id")
    spy.gem_returns["g-fast"] = "gem delivered"
    spy.install(monkeypatch)

    res = llm_mod.complete("Hi", tier="fast", preferences=MINI_PREFS)

    assert res.model_used == "gemini/g-fast"
    # Must have only ONE groq call — no retry for 400
    assert len(spy.groq_calls) == 1
    assert "400" in res.attempts[0].reason.lower()


# ---------------------------------------------------------------------------
# 6. json_mode + invalid JSON → retry on same model once with "Return ONLY valid JSON",
#    still bad → fall back to model 2 → model 2 succeeds
# ---------------------------------------------------------------------------

def test_json_invalid_retry_then_fallback(monkeypatch):
    spy = ProviderSpy()
    # groq returns non-JSON text twice (first call + JSON-retry extra call)
    spy.groq_returns["g-fast"] = "Sorry I can't do that right now."
    spy.gem_returns["g-fast"] = '{"ok": true}'
    spy.install(monkeypatch)

    res = llm_mod.complete(
        "Return {a: 1}", tier="fast", json_mode=True, preferences=MINI_PREFS
    )
    assert res.model_used == "gemini/g-fast"
    # groq: 1 normal call + 1 json-retry call = 2
    assert len(spy.groq_calls) == 2
    # Second groq call: prompt should contain the JSON hint
    second_prompt = spy.groq_calls[1][1]  # (model_id, prompt, system, json_mode, timeout)
    assert "return only valid json" in second_prompt.lower()
    # Attempts should include two "groq/g-fast" entries (initial + retry summary)
    groq_attempts = [a for a in res.attempts if a.model_spec == "groq/g-fast"]
    assert len(groq_attempts) >= 2


# ---------------------------------------------------------------------------
# 7. Missing GROQ_API_KEY → skip groq with clear reason, gemini used
# ---------------------------------------------------------------------------

def test_missing_api_key_skips_provider(monkeypatch):
    spy = ProviderSpy()
    spy.gem_returns["g-fast"] = "gem only reply"
    spy.install(monkeypatch)

    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    res = llm_mod.complete("Hi", tier="fast", preferences=MINI_PREFS)

    assert res.model_used == "gemini/g-fast"
    assert len(spy.groq_calls) == 0  # never called — skipped pre-call
    found = [a for a in res.attempts if a.model_spec == "groq/g-fast"]
    assert len(found) == 1
    assert "missing api key" in found[0].reason.lower()
    assert "GROQ_API_KEY" in found[0].reason


# ---------------------------------------------------------------------------
# 8. All models fail → AllModelsFailed exception with ordered attempts list
# ---------------------------------------------------------------------------

def test_all_models_failed_exception(monkeypatch):
    spy = ProviderSpy()
    spy.groq_raises["g-fast"] = RuntimeError("server error 500")
    spy.gem_raises["g-fast"] = RuntimeError("server error 500")
    spy.install(monkeypatch)

    with pytest.raises(AllModelsFailed) as excinfo:
        llm_mod.complete("Hi", tier="fast", preferences=MINI_PREFS)

    attempts = excinfo.value.attempts
    # Exactly 2 recorded attempts (1 per model, each summarised)
    assert len(attempts) >= 2
    assert attempts[0].model_spec == "groq/g-fast"
    assert attempts[-1].model_spec == "gemini/g-fast"
    # Exception message should contain the reason summary
    assert "All models failed" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 9. complete_json() → (parsed dict, LLMResult)
# ---------------------------------------------------------------------------

def test_complete_json_parses(monkeypatch):
    spy = ProviderSpy()
    spy.groq_returns["g-fast"] = '{"status":"ok","count":3}'
    spy.install(monkeypatch)

    data, res = llm_mod.complete_json(
        "Return this as JSON: {status: ok, count: 3}",
        tier="fast",
        preferences=MINI_PREFS,
    )

    assert data == {"status": "ok", "count": 3}
    assert res.model_used == "groq/g-fast"
    assert res.text == '{"status":"ok","count":3}'


# ---------------------------------------------------------------------------
# 10. SARADAR_FORCE_FAIL env hook forces provider-specific failure + fallback
# ---------------------------------------------------------------------------

def test_SARADAR_FORCE_FAIL_hook(monkeypatch):
    spy = ProviderSpy()
    spy.groq_returns["g-fast"] = "won't be used — force fail wins"
    spy.gem_returns["g-fast"] = "success via gem after force-fail"
    spy.install(monkeypatch)

    monkeypatch.setenv("SARADAR_FORCE_FAIL", "groq")

    res = llm_mod.complete("Hi", tier="fast", preferences=MINI_PREFS)

    assert res.model_used == "gemini/g-fast"
    assert len(spy.groq_calls) == 0  # _call_groq was NOT invoked
    found = [a for a in res.attempts if a.model_spec == "groq/g-fast"]
    assert len(found) == 1
    assert "force-fail" in found[0].reason.lower()
    # And groq is now cooled (force-fail returns as 429-type)
    assert "groq/g-fast" in _cooldown
