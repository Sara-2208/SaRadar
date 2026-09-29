"""Configuration loader for SaRadar.

Loads user preferences from config/preferences.yaml and secrets from
environment variables / .env file.
"""

import os
from pathlib import Path
from typing import Any, Dict, List

import yaml
from dotenv import load_dotenv

# TODO: Use Pydantic models for type-safe config validation
# TODO: Add config schema validation with helpful error messages


def load_dotenv_file() -> None:
    """Load environment variables from the .env file.

    Called once at import time. Secrets should be accessed via
    os.getenv after this call.
    """
    # TODO: Handle missing .env gracefully with a warning
    load_dotenv()


def load_preferences(config_path: str | Path | None = None) -> Dict[str, Any]:
    """Load user preferences from the YAML config file.

    Args:
        config_path: Path to preferences.yaml. Defaults to
            ``config/preferences.yaml`` relative to the project root.

    Returns:
        Dict with keys: roles, areas, max_distance_km, skip_title_keywords,
        fit_alert_threshold, llm_fallback_order.
    """
    # TODO: Validate config keys exist and have correct types
    # TODO: Support user-level config override in home directory
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "config" / "preferences.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_api_key(name: str) -> str | None:
    """Retrieve an API key from environment variables.

    Args:
        name: Environment variable name (e.g. ``GROQ_API_KEY``).

    Returns:
        The key string, or ``None`` if not set.
    """
    # TODO: Add validation that key is non-empty when required
    return os.getenv(name)


def get_llm_fallback_order(preferences: Dict[str, Any] | None = None) -> List[str]:
    """Return the ordered list of LLM providers to try.

    Args:
        preferences: Loaded preferences dict (auto-loaded if None).

    Returns:
        List of provider names, e.g. ``["groq", "gemini"]``.
    """
    if preferences is None:
        preferences = load_preferences()
    return preferences.get("llm_fallback_order", ["groq", "gemini"])


# Auto-load .env on module import
load_dotenv_file()
