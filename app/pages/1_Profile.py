"""👤 Profile page: upload resume, review/edit every field, save to DB.

Run: streamlit run app/Home.py  -> Profile
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from saradar import db as db_mod  # noqa: E402
from saradar import resume_parser as rp  # noqa: E402
from saradar.schemas import (  # noqa: E402
    ActivityEntry,
    EducationEntry,
    ExperienceEntry,
    Links,
    Profile,
    ProjectEntry,
    ScannedPDFError,
    SkillGroup,
)

st.set_page_config(page_title="Profile · SaRadar", page_icon="👤", layout="wide")
st.title("👤 Profile")
st.caption("Upload your resume, check every field, then save. SaRadar never invents experience.")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

db_mod.init_db()
ss = st.session_state
if "profile" not in ss:
    ss.profile = db_mod.load_profile() or Profile()
ss.setdefault("form_version", 0)   # bump to refresh all widgets after parse/reload
ss.setdefault("parse_info", None)  # {"models": [...], "warnings": [...], "chars": int}
ss.setdefault("resume_text", None)
ss.setdefault("unsaved", False)

profile: Profile = ss.profile
v = ss.form_version


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(val: Any) -> str | None:
    """Empty / NaN / None -> None, else stripped string."""
    if val is None:
        return None
    if not isinstance(val, str) and pd.isna(val):
        return None
    text = str(val).strip()
    return text or None


def _split_csv(raw: str) -> list[str]:
    """Split on commas, but not commas inside brackets: 'VM (a, b)' stays one item."""
    parts = re.split(r",\s*(?![^()]*\))", raw or "")
    return [p.strip() for p in parts if p.strip()]


def _split_lines(raw: str) -> list[str]:
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


def _table(rows: list[dict], cols: list[str], labels: dict[str, str], key: str) -> list[dict]:
    """Editable table. Returns cleaned rows, dropping fully empty ones."""
    df = pd.DataFrame(rows, columns=cols)
    cfg = {c: st.column_config.TextColumn(labels.get(c, c.capitalize())) for c in cols}
    edited = st.data_editor(df, num_rows="dynamic", hide_index=True, column_config=cfg, key=key)
    out = []
    for rec in edited.to_dict("records"):
        row = {c: _clean(rec.get(c)) for c in cols}
        if any(row.values()):
            out.append(row)
    return out


def _bullet_editors(rows: list[dict], originals: list, label: str, key_prefix: str) -> list[list[str]]:
    """One expander per row with a bullets text area."""
    result = []
    for i, row in enumerate(rows):
        orig = originals[i].bullets if i < len(originals) else []
        title = row.get(label) or "(untitled)"
        with st.expander(f"📝 {title}: bullets"):
            raw = st.text_area(
                "One bullet per line",
                value="\n".join(orig),
                height=110,
                key=f"{key_prefix}_{v}_{i}",
            )
        result.append(_split_lines(raw))
    return result


def _rows(items: list, cols: list[str]) -> list[dict]:
    return [{c: (getattr(item, c) or "") for c in cols} for item in items]


# ---------------------------------------------------------------------------
# Sidebar: upload + parse
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📥 Upload resume")
    uploaded = st.file_uploader("PDF only", type=["pdf"], key="resume_upload")
    if st.button("🔍 Parse with AI", type="primary", disabled=uploaded is None):
        try:
            with st.spinner("Reading PDF…"):
                text = rp.extract_text(uploaded.getvalue())
            with st.spinner("Extracting your profile with AI (10 to 30s)…"):
                outcome = rp.parse_resume_full(text)
        except ScannedPDFError as e:
            st.error(f"⚠️ {e}")
        except Exception as e:  # noqa: BLE001
            st.error(f"❌ AI parsing failed: {e}")
        else:
            ss.profile = outcome.profile
            ss.resume_text = rp._strip_references(text)  # never store referees
            ss.parse_info = {
                "models": outcome.models_used,
                "warnings": outcome.warnings,
                "chars": len(text),
            }
            ss.unsaved = True
            ss.form_version += 1
            st.rerun()

    if ss.parse_info:
        st.caption(
            f"Parsed with: {', '.join(ss.parse_info['models'])} · "
            f"{ss.parse_info['chars']} chars"
        )

    st.divider()
    if st.button("↩️ Discard changes (reload saved)"):
        ss.profile = db_mod.load_profile() or Profile()
        ss.parse_info = None
        ss.unsaved = False
        ss.form_version += 1
        st.rerun()


# ---------------------------------------------------------------------------
# Banners
# ---------------------------------------------------------------------------

if ss.unsaved:
    st.info("🟡 Parsed but **not saved yet**. Review each tab, then click **Save profile** at the bottom.")
if ss.parse_info:
    for w in ss.parse_info["warnings"]:
        st.warning(f"⚠️ {w}")


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

t_basic, t_exp, t_edu, t_proj, t_act = st.tabs(
    ["📋 Basics & Skills", "💼 Experience", "🎓 Education", "🏆 Projects", "🌟 Activities"]
)

with t_basic:
    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input("Name", value=profile.name or "", key=f"name_{v}")
        headline = st.text_input("Headline", value=profile.headline or "", key=f"headline_{v}")
        email = st.text_input("Email", value=profile.email or "", key=f"email_{v}")
        phone = st.text_input("Phone", value=profile.phone or "", key=f"phone_{v}")
        location = st.text_input("Location", value=profile.location or "",
                                 placeholder="e.g. Kuala Lumpur", key=f"location_{v}")
    with c2:
        github = st.text_input("GitHub", value=profile.links.github or "", key=f"github_{v}")
        linkedin = st.text_input("LinkedIn", value=profile.links.linkedin or "", key=f"linkedin_{v}")
        portfolio = st.text_input("Portfolio", value=profile.links.portfolio or "", key=f"portfolio_{v}")
        summary = st.text_area("Summary", value=profile.summary or "", height=150, key=f"summary_{v}")

    st.subheader("🛠️ Skills")
    s1, s2, s3 = st.columns(3)
    with s1:
        tech_raw = st.text_area("Programming languages (comma separated)",
                                value=", ".join(profile.skills.technical), height=120, key=f"tech_{v}")
    with s2:
        tools_raw = st.text_area("Tools & platforms (comma separated)",
                                 value=", ".join(profile.skills.tools), height=120, key=f"tools_{v}")
    with s3:
        soft_raw = st.text_area("Soft skills (comma separated)",
                                value=", ".join(profile.skills.soft), height=120, key=f"soft_{v}")

    l1, l2 = st.columns(2)
    with l1:
        certs_raw = st.text_area("🏅 Certifications (one per line)",
                                 value="\n".join(profile.certifications), height=100, key=f"certs_{v}")
    with l2:
        langs_raw = st.text_area("🌍 Languages (one per line)",
                                 value="\n".join(profile.languages), height=100, key=f"langs_{v}")

with t_exp:
    exp_cols = ["title", "company", "location", "start", "end"]
    exp_rows = _table(_rows(profile.experience, exp_cols), exp_cols, {}, key=f"exp_{v}")
    exp_bullets = _bullet_editors(exp_rows, profile.experience, "title", "expb")

with t_edu:
    edu_cols = ["degree", "field", "institution", "start", "end", "grade"]
    edu_rows = _table(_rows(profile.education, edu_cols), edu_cols, {}, key=f"edu_{v}")
    edu_bullets = _bullet_editors(edu_rows, profile.education, "degree", "edub")

with t_proj:
    st.caption("Projects, competitions and hackathons. Result = e.g. Champion, Top 10 Finalist.")
    proj_cols = ["name", "role", "result", "level", "date", "description", "tech"]
    proj_src = [
        {**{c: (getattr(p, c) or "") for c in proj_cols if c != "tech"}, "tech": ", ".join(p.tech)}
        for p in profile.projects
    ]
    proj_rows = _table(proj_src, proj_cols, {"tech": "Tech (comma separated)"}, key=f"proj_{v}")

with t_act:
    st.caption("Leadership, committees, volunteering, exchange programmes.")
    act_cols = ["title", "organization", "role", "start", "end"]
    act_rows = _table(_rows(profile.activities, act_cols), act_cols, {}, key=f"act_{v}")
    act_bullets = _bullet_editors(act_rows, profile.activities, "title", "actb")


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def _collect() -> Profile:
    return Profile(
        name=_clean(name),
        headline=_clean(headline),
        email=_clean(email),
        phone=_clean(phone),
        location=_clean(location),
        links=Links(github=_clean(github), linkedin=_clean(linkedin), portfolio=_clean(portfolio)),
        summary=_clean(summary),
        skills=SkillGroup(
            technical=_split_csv(tech_raw),
            tools=_split_csv(tools_raw),
            soft=_split_csv(soft_raw),
        ),
        experience=[ExperienceEntry(**r, bullets=exp_bullets[i]) for i, r in enumerate(exp_rows)],
        education=[EducationEntry(**r, bullets=edu_bullets[i]) for i, r in enumerate(edu_rows)],
        projects=[
            ProjectEntry(**{k: val for k, val in r.items() if k != "tech"},
                         tech=_split_csv(r.get("tech") or ""))
            for r in proj_rows
        ],
        activities=[ActivityEntry(**r, bullets=act_bullets[i]) for i, r in enumerate(act_rows)],
        certifications=_split_lines(certs_raw),
        languages=_split_lines(langs_raw),
    )


st.divider()
if st.button("💾 Save profile", type="primary"):
    try:
        new_prof = _collect()
    except ValidationError as e:
        st.error(f"❌ Invalid fields: {e}")
    else:
        try:
            db_mod.save_profile(new_prof, raw_text=ss.resume_text)
        except Exception as e:  # noqa: BLE001
            st.error(f"❌ Failed to save: {e}")
        else:
            ss.profile = new_prof
            ss.unsaved = False
            st.success("✅ Profile saved!")