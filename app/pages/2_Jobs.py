"""🔍 Jobs page (Phase 4C): fetch, score, filter and review jobs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from saradar import db as db_mod  # noqa: E402
from saradar import job_store  # noqa: E402
from saradar.config import load_preferences  # noqa: E402
from saradar.jobs import BudgetExceeded, run_search  # noqa: E402
from saradar.pipeline import score_unscored  # noqa: E402
from saradar.schemas import JobRequirements  # noqa: E402
from saradar.scorer import FitResult, SkillMatch, explain_fit  # noqa: E402

st.set_page_config(page_title="Jobs · SaRadar", page_icon="🔍", layout="wide")
st.title("🔍 Jobs")

db_mod.init_db()
ss = st.session_state
ss.setdefault("why_cache", {})  # job hash -> explanation text

ICONS = {"exact": "✅", "similar": "🟢", "partial": "🟡", "missing": "❌"}
LABEL_COLOR = {"Strong fit": "green", "Fair fit": "orange", "Stretch": "red"}
PART_NAMES = {"must_have": "Must-have", "similarity": "Similarity", "seniority": "Seniority / years",
              "nice_to_have": "Nice-to-have", "location": "Location"}


def _fit_from_json(raw: str) -> FitResult:
    d = json.loads(raw)
    return FitResult(
        score=d["score"], label=d["label"], breakdown=d["breakdown"],
        must_have=[SkillMatch(**m) for m in d["must_have"]],
        nice_to_have=[SkillMatch(**m) for m in d["nice_to_have"]],
        confidence=d["confidence"], notes=d.get("notes", []),
    )


# ---------------------------------------------------------------------------
# Top bar: fetch + score
# ---------------------------------------------------------------------------

prefs = load_preferences()
budget = int((prefs.get("job_search") or {}).get("monthly_budget", 180))
used = job_store.get_usage("jsearch")
queries = (prefs.get("job_search") or {}).get("queries", [])

a, b, c = st.columns([2, 2, 3])
with a:
    if st.button(f"🔄 Fetch & score ({len(queries)} searches)", type="primary",
                 disabled=used + len(queries) > budget):
        try:
            with st.spinner("Searching jobs…"):
                rep = run_search()
            st.toast(f"Fetched {rep.fetched}, kept {len(rep.kept)}, new {len(rep.new)}")
            if rep.new:
                with st.spinner(f"Scoring {len(rep.new)} new jobs…"):
                    score_unscored(limit=len(rep.new) + 5)
            st.rerun()
        except BudgetExceeded as e:
            st.error(f"⛔ {e}")
        except Exception as e:  # noqa: BLE001
            st.error(f"❌ Fetch failed: {e}")
with b:
    if st.button("🎯 Score unscored jobs"):
        with st.spinner("Scoring…"):
            rep = score_unscored(limit=20)
        if rep.no_profile:
            st.warning("Save your profile first (👤 Profile).")
        else:
            st.toast(f"Scored {len(rep.scored)}, failed {len(rep.failed)}")
            st.rerun()
with c:
    st.caption(f"JSearch quota this month: **{used}/{budget}** used")
    st.progress(min(used / budget, 1.0) if budget else 0.0)

st.divider()

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

jobs = job_store.list_jobs(limit=500)
if not jobs:
    st.info("No jobs yet. Click **Fetch & score** to find jobs.")
    st.stop()

f1, f2, f3, f4 = st.columns([2, 3, 1, 2])
min_fit = f1.slider("Min fit %", 0, 100, 0, step=5)
labels = f2.multiselect("Labels", ["Strong fit", "Fair fit", "Stretch"],
                        default=["Strong fit", "Fair fit", "Stretch"])
only_new = f3.checkbox("🆕 only")
keyword = f4.text_input("Search", placeholder="title or company")


def _keep(j: Dict[str, Any]) -> bool:
    if only_new and not j["is_new"]:
        return False
    if j["fit"] is not None:
        if j["fit"] < min_fit or (j["fit_label"] and j["fit_label"] not in labels):
            return False
    kw = keyword.lower().strip()
    return not kw or kw in f"{j['title']} {j['company']}".lower()


shown = [j for j in jobs if _keep(j)]
st.caption(f"Showing **{len(shown)}** of {len(jobs)} jobs · best fit first")

# ---------------------------------------------------------------------------
# Job cards
# ---------------------------------------------------------------------------

for j in shown:
    fit = _fit_from_json(j["fit_json"]) if j.get("fit_json") else None
    with st.container(border=True):
        left, right = st.columns([5, 1])
        with left:
            new = "🆕 " if j["is_new"] else ""
            st.markdown(f"#### {new}{j['title']}")
            where = ", ".join(filter(None, [j.get("city"), j.get("state")])) or "Location unknown"
            posted = (j.get("posted_at") or "")[:10]
            meta = [j["company"], where, j.get("work_mode"), f"via {j.get('publisher')}", posted]
            st.caption(" · ".join(filter(None, meta)))
            if j.get("jd_status") == "partial":
                st.caption("⚠️ Short job summary only; score is rough. Open the job for full details.")
        with right:
            if fit:
                color = LABEL_COLOR.get(fit.label, "gray")
                st.metric("Fit", f"{fit.score}%")
                st.markdown(f":{color}[**{fit.label}**]")
            else:
                st.metric("Fit", "–")
                st.caption("Not scored")

        if fit:
            with st.expander("Details"):
                for key, val in fit.breakdown.items():
                    x1, x2 = st.columns([1, 3])
                    x1.write(f"{PART_NAMES.get(key, key)}: **{val}**")
                    x2.progress(val / 100)
                if fit.must_have:
                    st.dataframe([{
                        "": ICONS[m.kind], "Requirement": m.requirement, "Match": m.kind,
                        "Your evidence": (m.evidence or "")[:110],
                    } for m in fit.must_have], hide_index=True)
                for n in fit.notes:
                    st.caption(f"• {n}")

                if j["hash"] in ss.why_cache:
                    st.info(ss.why_cache[j["hash"]])
                elif st.button("💬 Why this score?", key=f"why_{j['hash']}"):
                    req = JobRequirements.model_validate_json(j["requirements_json"])
                    with st.spinner("Writing explanation…"):
                        ss.why_cache[j["hash"]] = explain_fit(fit, req)
                    st.rerun()

        b1, b2, _ = st.columns([1, 1, 4])
        if j.get("url"):
            b1.link_button("Open job ↗", j["url"])
        if j["is_new"] and b2.button("✔ Mark seen", key=f"seen_{j['hash']}"):
            job_store.mark_seen(j["hash"])
            st.rerun()