"""✨ Tailor page. Tab 1: Fit Check (Phase 3C). Tab 2: Tailoring (Phase 5)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from saradar import db as db_mod  # noqa: E402
from saradar.requirements_extractor import extract_requirements  # noqa: E402
from saradar.scorer import explain_fit, score_fit  # noqa: E402

st.set_page_config(page_title="Tailor · SaRadar", page_icon="✨", layout="wide")
st.title("✨ Tailor")

db_mod.init_db()
profile = db_mod.load_profile()
if not profile:
    st.warning("No saved profile yet. Go to **👤 Profile**, parse your resume, and save it first.")
    st.stop()

ss = st.session_state
ss.setdefault("fit_state", None)  # {"req": ..., "fit": ..., "why": ...}

ICONS = {"exact": "✅", "similar": "🟢", "partial": "🟡", "missing": "❌"}
LABEL_COLOR = {"Strong fit": "green", "Fair fit": "orange", "Stretch": "red"}

tab_fit, tab_tailor = st.tabs(["🎯 Fit check", "📝 Tailor resume (coming soon)"])

with tab_fit:
    st.caption("Paste a job description to see how well you fit, and why.")
    c1, c2, c3 = st.columns(3)
    title = c1.text_input("Job title (optional)")
    company = c2.text_input("Company (optional)")
    location = c3.text_input("Location (optional)", placeholder="e.g. Kuala Lumpur")
    jd_text = st.text_area("Job description", height=260,
                           placeholder="Paste the full job description here…")

    if st.button("🎯 Check my fit", type="primary", disabled=not jd_text.strip()):
        try:
            with st.spinner("Reading job requirements…"):
                req, _ = extract_requirements(jd_text, title=title or None,
                                              company=company or None,
                                              location=location or None)
            with st.spinner("Scoring your fit (first time loads the matching model)…"):
                fit = score_fit(profile, req, jd_text=jd_text)
            with st.spinner("Writing a short explanation…"):
                why = explain_fit(fit, req)
        except Exception as e:  # noqa: BLE001
            st.error(f"❌ Fit check failed: {e}")
        else:
            ss.fit_state = {"req": req, "fit": fit, "why": why}

    state = ss.fit_state
    if state:
        req, fit, why = state["req"], state["fit"], state["why"]
        st.divider()

        top1, top2 = st.columns([1, 2])
        with top1:
            st.metric("Fit score", f"{fit.score}%")
            color = LABEL_COLOR.get(fit.label, "gray")
            st.markdown(f":{color}[**{fit.label}**] · confidence: **{fit.confidence}**")
            if req.title or req.company:
                st.caption(" · ".join(filter(None, [req.title, req.company, req.location])))
        with top2:
            st.markdown("**Why**")
            st.write(why)

        st.markdown("**Breakdown**")
        names = {"must_have": "Must-have skills", "similarity": "Overall similarity",
                 "seniority": "Seniority / years", "nice_to_have": "Nice-to-have",
                 "location": "Location"}
        for key, val in fit.breakdown.items():
            b1, b2 = st.columns([1, 3])
            b1.write(f"{names.get(key, key)}: **{val}**")
            b2.progress(val / 100)

        for heading, items in (("Must-have", fit.must_have), ("Nice-to-have", fit.nice_to_have)):
            st.markdown(f"**{heading}**")
            if not items:
                st.caption("None listed in this job.")
                continue
            rows = [{
                "": ICONS[m.kind],
                "Requirement": m.requirement,
                "Match": m.kind,
                "Your evidence": (m.evidence or "")[:120],
            } for m in items]
            st.dataframe(rows, hide_index=True)

        if fit.notes:
            st.markdown("**Notes**")
            for n in fit.notes:
                st.caption(f"• {n}")

        with st.expander("🔎 Extracted requirements (raw)"):
            st.json(req.model_dump())

with tab_tailor:
    st.info("Resume tailoring arrives in Phase 5. It will use the fit check above "
            "to rewrite your bullets for this job, using only your real experience.")