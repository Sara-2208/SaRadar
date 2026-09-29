# SaRadar

SaRadar: AI job radar that finds roles matching your skills, explains your fit, and alerts you the moment they're posted.

## ⚠️ Non-negotiable Rules

These rules are hard constraints. Never bypass them, even if a user asks to.

### 1. Never invent resume experience
The tailor module **only rephrases and re-orders** existing bullets from the user's resume. It must never fabricate companies, roles, dates, projects, metrics, or achievements. All tailored output must be traceable to input via an audit trail.

### 2. No scraping LinkedIn / JobStreet
Jobs may only be sourced from:
- **Official APIs** (e.g. RapidAPI-listed job APIs)
- **Gmail job alerts** (parsed via the official Gmail API from emails sent by job boards)

No web scraping, headless browsing, or reverse-engineering of protected job sites.

### 3. User approves every action; never auto-apply
SaRadar is a decision-support tool, not an auto-apply bot:
- Tailored resumes are **drafts only** — user must review and edit before use.
- Application tracking entries are created **only when the user confirms** they applied.
- Telegram alerts are **read-only notifications** — no auto-submit of any form anywhere.

---

## Stack

- **Frontend / UI:** Streamlit (`app/`)
- **API:** FastAPI (`api/main.py`)
- **Core logic:** Python package `saradar/`
- **Storage:** SQLite (`data/saradar.db`, ignored by git)
- **Config:** YAML preferences + `.env` secrets
- **Notifications:** Telegram Bot API
- **LLM:** Groq, Google Gemini (via LiteLLM abstraction with fallback)
- **Tests:** pytest (`tests/`)
- **Orchestration:** n8n workflows (placeholder in `automation/`)
