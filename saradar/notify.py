"""Telegram notifications: daily job digest (auto-split, HTML formatted)."""

from __future__ import annotations

import html
import os
from typing import Any, Dict, List, Optional

import requests

from saradar.config import get_api_key

TELEGRAM_LIMIT = 4000
ICON = {"Strong fit": "🟢", "Fair fit": "🟠", "Stretch": "🔴"}
HEADER = "📡 <b>SaRadar daily</b>"


def _key(name: str) -> Optional[str]:
    return get_api_key(name) or os.getenv(name)


def _job_line(i: int, j: Dict[str, Any]) -> str:
    icon = ICON.get(j.get("fit_label"), "⚪")
    title = html.escape(j.get("title") or "")
    company = html.escape(j.get("company") or "")
    area = html.escape(j.get("city") or j.get("state") or "?")
    short = " ⚠️ short JD" if j.get("jd_status") == "partial" else ""
    link = f' · <a href="{html.escape(j["url"], quote=True)}">Open</a>' if j.get("url") else ""
    return f"{i}. {icon} <b>{int(j['fit'])}%</b> {title}{short}\n    {company} · {area}{link}"


def build_digest(
    jobs: List[Dict[str, Any]],
    min_fit: int = 50,
    max_jobs: int = 0,
    show_stretch_count: bool = True,
) -> List[str]:
    """Build message chunks. Empty list = nothing worth sending."""
    scored = sorted([j for j in jobs if j.get("fit") is not None],
                    key=lambda j: j["fit"], reverse=True)
    listed = [j for j in scored if j["fit"] >= min_fit]
    below = len(scored) - len(listed)
    if not listed:
        return []

    hidden = 0
    if max_jobs and max_jobs > 0 and len(listed) > max_jobs:
        hidden = len(listed) - max_jobs
        listed = listed[:max_jobs]

    blocks = [_job_line(i, j) for i, j in enumerate(listed, 1)]
    if hidden:
        blocks.append(f"+{hidden} more at {min_fit}%+ in SaRadar")
    if show_stretch_count and below:
        blocks.append(f"+{below} below {min_fit}%. Open SaRadar to see all.")

    chunks: List[str] = []
    current = f"{HEADER}: {len(scored)} new jobs, {len(listed) + hidden} at {min_fit}%+"
    for block in blocks:
        if len(current) + len(block) + 2 > TELEGRAM_LIMIT:
            chunks.append(current)
            current = f"{HEADER} (cont.)"
        current += "\n\n" + block
    chunks.append(current)
    return chunks


def empty_message() -> str:
    return f"{HEADER}: no new jobs today."


def send_telegram(text: str, token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
    token = token or _key("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or _key("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing in .env")
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": "true"},
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"Telegram error {resp.status_code}: {resp.text[:200]}")