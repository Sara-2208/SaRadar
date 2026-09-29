# Automation — n8n Workflows

This folder contains n8n workflow definitions (placeholder).

## Planned workflows

1. **Job ingestion trigger** — runs hourly:
   - Calls SaRadar API / jobs.py to fetch from RapidAPI + Gmail alerts
   - Normalizes, deduplicates, and writes to `jobs` table
   - Marks new jobs with `is_new = 1`

2. **Fit scoring + alerting** — runs every 15 minutes:
   - Picks up `jobs.jd_status = 'pending'` rows
   - Calls scorer.compute_fit_score() using candidate profile
   - Writes fit score + explanation back
   - If fit >= fit_alert_threshold AND is_new: triggers Telegram notify

3. **Daily digest** — runs at 09:00 daily:
   - Compiles all new high-fit jobs from the past 24h
   - Sends a single Telegram digest

## TODO

- [ ] Export n8n workflow JSON once built
- [ ] Document required n8n credentials (Telegram, SQLite, RapidAPI proxy)
- [ ] Add failure recovery + retries with backoff
