"""LLM abstraction layer with tiered model fallback.

Reads model tiers from the ``llm`` section of ``config/preferences.yaml``::

    llm:
      fast:   [groq/openai/gpt-oss-20b, gemini/gemini-3.5-flash-lite, ...]
      smart:  [groq/openai/gpt-oss-120b, gemini/gemini-3.8-flash, ...]
      timeout_seconds: 30
      max_retries: 1

Other modules call the top-level functions:

.. code-block:: python

    from saradar import llm
    result = llm.complete("Hi", system="You are helpful.", tier="fast")
    data, result = llm.complete_json("Return a list of 3 skills.")
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from saradar.config import get_api_key, load_preferences

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("saradar.llm")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FailedAttempt:
    """A single failed model try, kept for transparency in LLMResult.attempts."""
    model_spec: str
    reason: str


@dataclass
class LLMResult:
    """Result of a successful :func:`complete` call.

    Attributes:
        text: The raw response text from the winning model.
        model_used: The full spec that answered, e.g. ``"groq/openai/gpt-oss-20b"``.
        attempts: Any model specs that were tried and failed *before* the winner,
            plus any specs skipped upfront (missing key, cooled down).
    """
    text: str
    model_used: str
    attempts: List[FailedAttempt] = field(default_factory=list)


class AllModelsFailed(Exception):
    """Raised by :func:`complete` when *every* model in the tier failed."""

    def __init__(self, attempts: List[FailedAttempt]):
        self.attempts = attempts
        summary = "; ".join(f"{a.model_spec}: {a.reason}" for a in attempts) or "no attempts"
        super().__init__(f"All models failed. Attempts: {summary}")


# ---------------------------------------------------------------------------
# Module-level shared state
# ---------------------------------------------------------------------------

# One Gemini client kept alive for the whole process lifetime — do NOT recreate in a loop.
_gemini_client: Any = None

# per-model-spec 429 cooldown expiry (utc datetime); skip model while now < expiry
_cooldown: Dict[str, datetime] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_model_spec(model_spec: str) -> Tuple[str, str]:
    """Split a tier-entry spec into (provider, model_id).

    ``"groq/openai/gpt-oss-20b"`` -> ``("groq", "openai/gpt-oss-20b")``
    ``"gemini/gemini-3.5-flash-lite"`` -> ``("gemini", "gemini-3.5-flash-lite")``
    """
    provider, _, model_id = model_spec.partition("/")
    if not provider or not model_id:
        raise ValueError(f"Invalid model spec (need provider/model): {model_spec!r}")
    return provider, model_id


def _get_tier_config(preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return the whole ``llm:`` dict from preferences with sensible defaults."""
    prefs = preferences if preferences is not None else load_preferences()
    llm_cfg = prefs.get("llm") or {}
    return {
        "fast": llm_cfg.get("fast", ["groq/openai/gpt-oss-20b", "gemini/gemini-2.5-flash"]),
        "smart": llm_cfg.get("smart", ["groq/openai/gpt-oss-120b", "gemini/gemini-2.5-flash"]),
        "timeout_seconds": int(llm_cfg.get("timeout_seconds", 30)),
        "max_retries": int(llm_cfg.get("max_retries", 1)),
    }


def _is_cooled_down(model_spec: str) -> bool:
    """Return True if ``model_spec`` is still 429-cooled (should be skipped)."""
    expiry = _cooldown.get(model_spec)
    if expiry is None:
        return False
    if datetime.utcnow() >= expiry:
        _cooldown.pop(model_spec, None)
        return False
    return True


def _force_fail_providers() -> List[str]:
    """Read SARADAR_FORCE_FAIL env var: comma-separated provider names to artificially fail."""
    raw = os.environ.get("SARADAR_FORCE_FAIL", "")
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


# ---------------------------------------------------------------------------
# Provider calls
# ---------------------------------------------------------------------------


def _ensure_gemini_client() -> Any:
    """Return the module-level Gemini client, initialising once lazily."""
    global _gemini_client
    if _gemini_client is None:
        from google import genai  # import lazily so it's not required at import-time
        key = get_api_key("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
        _gemini_client = genai.Client(api_key=key)
    return _gemini_client


def _call_groq(
    model_id: str,
    prompt: str,
    system: Optional[str],
    json_mode: bool,
    timeout_seconds: int,
    max_tokens: int,
) -> str:
    """Call Groq chat completion via the official ``groq`` SDK.

    When ``json_mode`` is True we *also* append "Respond in JSON." to the
    system prompt because Groq requires the word JSON in the context for
    ``response_format=json_object`` to work reliably.
    """
    from groq import Groq

    key = get_api_key("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
    client = Groq(api_key=key, timeout=timeout_seconds)

    effective_system = system or ""
    if json_mode:
        effective_system = (effective_system + "\nRespond in JSON.").strip()

    messages: List[Dict[str, str]] = []
    if effective_system:
        messages.append({"role": "system", "content": effective_system})
    messages.append({"role": "user", "content": prompt})

    kwargs: Dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


def _call_gemini(
    model_id: str,
    prompt: str,
    system: Optional[str],
    json_mode: bool,
    timeout_seconds: int,
    max_tokens: int,
) -> str:
    """Call Gemini via the *new* ``google-genai`` SDK using ``types.GenerateContentConfig``."""
    from google.genai import types

    client = _ensure_gemini_client()

    config_kwargs: Dict[str, Any] = {}
    if system:
        config_kwargs["system_instruction"] = system
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
    config_kwargs["http_options"] = types.HttpOptions(timeout=timeout_seconds * 1000)
    config_kwargs["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(
        disable=True,
    )
    config_kwargs["max_output_tokens"] = max_tokens
    config = types.GenerateContentConfig(**config_kwargs)

    response = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config=config,
    )
    return response.text or ""


# ---------------------------------------------------------------------------
# Single-model try (with retries & testing hook)
# ---------------------------------------------------------------------------


def _try_model(
    model_spec: str,
    prompt: str,
    system: Optional[str],
    json_mode: bool,
    timeout_seconds: int,
    max_retries: int,
    max_tokens: int,
) -> Tuple[Optional[str], Optional[str], bool]:
    """Attempt *one* model spec with retry logic.

    Returns:
        ``(text, failure_reason, is_429)``.
        On success: ``(text, None, False)``.
        On failure: ``(None, reason_str, rate_limited_bool)``.
    """
    provider, model_id = _parse_model_spec(model_spec)

    # Testing hook: pretend a provider always fails with 429
    if provider.lower() in _force_fail_providers():
        return None, "force-failed via SARADAR_FORCE_FAIL", True

    total_attempts = 1 + max(max_retries, 0)  # first try + retries
    last_reason: Optional[str] = None

    for attempt in range(1, total_attempts + 1):
        try:
            if provider.lower() == "groq":
                text = _call_groq(model_id, prompt, system, json_mode, timeout_seconds, max_tokens)
            elif provider.lower() == "gemini":
                text = _call_gemini(model_id, prompt, system, json_mode, timeout_seconds, max_tokens)
            else:
                return None, f"unknown provider: {provider}", False
            return text, None, False
        except Exception as exc:  # noqa: BLE001 — we classify below
            msg = str(exc).lower()
            # --- classification ---------------------------------------------------
            is_429 = any(k in msg for k in ("429", "rate limit", "quota", "too many requests"))
            is_5xx = any(k in msg for k in ("500", "502", "503", "504", "server error", "bad gateway"))
            is_400 = any(k in msg for k in ("400 ", "bad request", "invalid request"))
            is_timeout = "timeout" in msg or "timed out" in msg or "deadline" in msg
            # ----------------------------------------------------------------------
            if is_429:
                return None, f"429 rate limited: {exc}", True
            if is_400:
                return None, f"400 bad request: {exc}", False
            if is_timeout or is_5xx:
                last_reason = f"timeout/5xx (attempt {attempt}/{total_attempts}): {exc}"
                if attempt < total_attempts:
                    time.sleep(min(1.0 * attempt, 2.0))  # tiny backoff
                    continue
                return None, last_reason, False
            # Any other error (bad auth, model not found, etc.) → next model, no retry
            return None, f"{type(exc).__name__}: {exc}", False

    # Should be unreachable (returned inside loop on last attempt)
    return None, last_reason or "unknown", False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def complete(
    prompt: str,
    system: Optional[str] = None,
    tier: str = "fast",
    json_mode: bool = False,
    max_tokens: Optional[int] = None,
    preferences: Optional[Dict[str, Any]] = None,
) -> LLMResult:
    """Call the best-available model in ``tier`` with automatic fallback.

    Args:
        prompt: The user / instruction text.
        system: Optional system prompt.
        tier: ``"fast"`` or ``"smart"`` — selects which ordered model list to try.
        json_mode: Ask the provider to return JSON (via response_format / mime type).
            Note: you are strongly encouraged to also include the word "JSON" in
            the prompt or system prompt for best results.
        max_tokens: Override the output token budget. Defaults are generous:
            4096 for ``json_mode=True``, 2048 otherwise.
        preferences: Optional pre-loaded preferences dict (auto-loaded if None).

    Returns:
        :class:`LLMResult` with ``text``, ``model_used``, and any prior ``attempts``.

    Raises:
        AllModelsFailed: Every model in the tier failed or was skipped; the
            exception's ``.attempts`` list preserves full order + reasons.
    """
    cfg = _get_tier_config(preferences)
    try:
        models: List[str] = list(cfg[tier])
    except KeyError as exc:
        raise ValueError(f"Unknown tier {tier!r}; expected 'fast' or 'smart'.") from exc

    timeout = cfg["timeout_seconds"]
    max_retries = cfg["max_retries"]
    if max_tokens is None:
        max_tokens = 4096 if json_mode else 2048
    attempts: List[FailedAttempt] = []
    effective_prompt = prompt

    for idx, model_spec in enumerate(models):
        # 1) Cool-down skip (429 earlier this process)
        if _is_cooled_down(model_spec):
            remaining = int((_cooldown[model_spec] - datetime.utcnow()).total_seconds())
            reason = f"skipping: 429 cooldown active ({remaining}s remaining)"
            logger.info("[saradar.llm] %s — %s", model_spec, reason)
            attempts.append(FailedAttempt(model_spec, reason))
            continue

        # 2) Missing-API-key skip
        provider, _ = _parse_model_spec(model_spec)
        env_var = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY"}.get(provider.lower())
        key_value = get_api_key(env_var) or os.getenv(env_var) if env_var else None
        if env_var and not key_value:
            reason = f"missing API key ({env_var})"
            logger.info("[saradar.llm] %s — %s", model_spec, reason)
            attempts.append(FailedAttempt(model_spec, reason))
            continue

        # 3) Try the model (with retries for 5xx/timeout)
        text, fail_reason, was_429 = _try_model(
            model_spec, effective_prompt, system, json_mode, timeout, max_retries,
            max_tokens,
        )

        if was_429:
            _cooldown[model_spec] = datetime.utcnow() + timedelta(minutes=60)

        if text is not None:
            # --- model returned text; in json_mode also validate it's parseable ---
            text_is_valid_json = True
            if json_mode:
                try:
                    json.loads(text)
                except json.JSONDecodeError:
                    text_is_valid_json = False

            if not json_mode or text_is_valid_json:
                # Genuine success ---------------------------------------------------
                logger.info(
                    "[saradar.llm] answered by %s (%d prior attempts/fallbacks)",
                    model_spec, len(attempts),
                )
                for a in attempts:
                    logger.debug("  skipped/failed: %s — %s", a.model_spec, a.reason)
                return LLMResult(text=text, model_used=model_spec, attempts=attempts)

            # json_mode + unparseable text → treat as a failure, run JSON-retry below
            fail_reason = f"json_mode response failed to parse as JSON"
            logger.warning("[saradar.llm] %s: %s", model_spec, fail_reason)

        # --- failure: record & possibly JSON-retry on the SAME model -------------
        attempts.append(FailedAttempt(model_spec, fail_reason or "unknown failure"))

        # json_mode invalid-JSON special retry: try same model *once* extra with prompt tweak
        if json_mode and (
            _looks_like_invalid_json_failure(fail_reason, text)
            or (text is not None and fail_reason == "json_mode response failed to parse as JSON")
        ):
            retry_prompt = effective_prompt + "\n\nReturn ONLY valid JSON. No markdown, no explanations."
            logger.info("[saradar.llm] %s retrying once with 'Return ONLY valid JSON' prompt", model_spec)
            # Exactly one extra try (no further retries) so force max_retries=0
            text2, fail2, was_429_2 = _try_model(
                model_spec, retry_prompt, system, json_mode, timeout, max_retries=0,
                max_tokens=max_tokens,
            )
            if was_429_2 and model_spec not in _cooldown:
                _cooldown[model_spec] = datetime.utcnow() + timedelta(minutes=60)
            if text2 is not None:
                # Also validate JSON parse of text2 when in json_mode
                if not json_mode:
                    logger.info("[saradar.llm] answered by %s after JSON-retry", model_spec)
                    return LLMResult(text=text2, model_used=model_spec, attempts=attempts)
                try:
                    json.loads(text2)
                    logger.info("[saradar.llm] answered by %s after JSON-retry", model_spec)
                    return LLMResult(text=text2, model_used=model_spec, attempts=attempts)
                except json.JSONDecodeError as exc:
                    fail2 = f"json-retry also returned non-JSON: {exc}"
                    logger.warning("[saradar.llm] %s json-retry text not parseable: %s", model_spec, exc)
            if fail2:
                attempts.append(FailedAttempt(model_spec, f"json-retry: {fail2}"))
                logger.warning("[saradar.llm] %s json-retry also failed: %s", model_spec, fail2)

        # Next model in the tier list
        continue

    # --- all failed -----------------------------------------------------------
    logger.error("[saradar.llm] All %d models in tier %r failed.", len(models), tier)
    raise AllModelsFailed(attempts=attempts)


def _looks_like_invalid_json_failure(fail_reason: Optional[str], text: Optional[str]) -> bool:
    """Heuristic: did we *not* raise (text came back) but it's unparseable?

    Note: in :func:`complete` we only get here with a fail_reason that was
    set by the provider layer. We also peek at ``text``: if we somehow got
    non-JSON text back, downstream :func:`complete_json` will flag it, but
    we want the retry *here* in complete() before we give up on the model.
    """
    # When _try_model returned (None, reason) for JSON issues it would be
    # classified as "other". We re-check by running json.loads on the text
    # when it's not None.
    if text is None:
        return False
    try:
        json.loads(text)
        return False
    except Exception:
        return True


def complete_json(
    prompt: str,
    system: Optional[str] = None,
    tier: str = "fast",
    preferences: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], LLMResult]:
    """Convenience wrapper: :func:`complete` + JSON parse.

    If the winning model returns unparseable text (despite json_mode), we
    record it as a failure, append the attempt, and re-run :func:`complete`
    starting at the *next* model (so it cascades across the tier exactly
    like other fallbacks).

    Returns:
        ``(parsed_dict, llm_result)``.
    """
    cfg = _get_tier_config(preferences)
    models: List[str] = list(cfg[tier])
    all_attempts: List[FailedAttempt] = []
    start_from = 0

    while start_from < len(models):
        # Run complete but effectively only from index start_from onwards by
        # temporarily cooling-down (not really) preceding models — cleaner:
        # just pass an ad-hoc config that truncates the model list.
        sliced_cfg = dict(cfg)
        sliced_cfg[tier] = models[start_from:]
        sliced_prefs = {"llm": sliced_cfg}
        try:
            result = complete(prompt, system=system, tier=tier, json_mode=True, preferences=sliced_prefs)
        except AllModelsFailed as e:
            all_attempts.extend(e.attempts)
            raise AllModelsFailed(attempts=all_attempts) from e

        # Shift attempts back onto our global list (accounting for slice offset)
        all_attempts.extend(result.attempts)

        try:
            data = json.loads(result.text)
            final_result = LLMResult(text=result.text, model_used=result.model_used, attempts=all_attempts)
            return data, final_result
        except json.JSONDecodeError as exc:
            reason = f"invalid JSON in response: {exc}"
            logger.warning("[saradar.llm] %s returned non-JSON: %s", result.model_used, reason)
            all_attempts.append(FailedAttempt(result.model_used, reason))
            # Figure out where this model was in the full list and skip past it
            try:
                start_from = models.index(result.model_used) + 1
            except ValueError:
                start_from = len(models)
            continue

    raise AllModelsFailed(attempts=all_attempts)
