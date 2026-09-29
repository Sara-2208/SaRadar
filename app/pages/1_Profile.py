"""👤 Profile page — upload resume, edit fields, save to DB.

Run via Streamlit: ``streamlit run app/Home.py`` → navigate to Profile.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import streamlit as st
from pydantic import ValidationError

# Make imports work whether launched as module or via `streamlit run app/Home.py`
import sys as _sys
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from saradar import db as db_mod  # noqa: E402
from saradar import resume_parser  # noqa: E402
from saradar.schemas import (  # noqa: E402
    EducationEntry,
    ExperienceEntry,
    Profile,
    ProjectEntry,
    ScannedPDFError,
    SkillGroup,
)

st.set_page_config(page_title="Profile", page_icon="👤")
st.title("👤 Profile")

# ---------------------------------------------------------------------------
# DB init + session state bootstrap
# ---------------------------------------------------------------------------

db_mod.init_db()

if "profile" not in st.session_state:
    loaded = db_mod.load_profile()
    st.session_state.profile = loaded or Profile()
if "last_llm_model" not in st.session_state:
    st.session_state.last_llm_model = None
if "resume_raw_text" not in st.session_state:
    st.session_state.resume_raw_text = None

profile: Profile = st.session_state.profile


# ---------------------------------------------------------------------------
# Sidebar — resume upload + AI parse
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📥 Upload Resume")
    uploaded = st.file_uploader("PDF resume", type=["pdf"], key="profile_pdf_upload")
    parse_btn = st.button("🔍 Parse resume with AI", type="primary", disabled=uploaded is None)

    if parse_btn and uploaded is not None:
        try:
            file_bytes = uploaded.getvalue()
            with st.spinner("Extracting text from PDF…"):
                text = resume_parser.extract_text(file_bytes)
            st.session_state.resume_raw_text = text
            with st.spinner("Parsing with AI… (may take 5–15s)"):
                new_profile, llm_result = resume_parser.parse_resume(text)
            st.session_state.profile = new_profile
            st.session_state.last_llm_model = llm_result.model_used
            st.success(f"✅ Parsed successfully using {llm_result.model_used}")
            st.rerun()
        except ScannedPDFError as e:
            st.error(f"⚠️ {e}")
        except Exception as e:  # noqa: BLE001
            st.error(f"❌ AI parsing failed: {e}")

    if st.session_state.last_llm_model:
        st.caption(
            f"Last parsed using: `{st.session_state.last_llm_model}`"
            + (
                f" · Resume text: {len(st.session_state.resume_raw_text)} chars"
                if st.session_state.resume_raw_text
                else ""
            )
        )


# ---------------------------------------------------------------------------
# Main UI: split into two columns
# ---------------------------------------------------------------------------

c1, c2 = st.columns([1, 1])

# ---- Column 1 — basics + skills -------------------------------------------

with c1:
    st.subheader("📋 Basics")
    name = st.text_input("Name", value=profile.name or "", placeholder="e.g. Amirah Rahman")
    email = st.text_input("Email", value=profile.email or "", placeholder="you@example.com")
    phone = st.text_input("Phone", value=profile.phone or "", placeholder="+60 12-345 6789")
    location = st.text_input("Location", value=profile.location or "", placeholder="Kuala Lumpur, Malaysia")
    summary = st.text_area(
        "Professional summary",
        value=profile.summary or "",
        height=130,
        placeholder="2–3 sentences on your focus and expertise…",
    )

    st.subheader("🛠️ Skills")
    tech_raw = st.text_area(
        "Technical (comma separated)",
        value=", ".join(profile.skills.technical),
        height=90,
        placeholder="Python, SQL, PyTorch, TensorFlow…",
    )
    tools_raw = st.text_area(
        "Tools & Platforms (comma separated)",
        value=", ".join(profile.skills.tools),
        height=80,
        placeholder="Docker, AWS, GCP, MLflow…",
    )
    soft_raw = st.text_area(
        "Soft skills (comma separated)",
        value=", ".join(profile.skills.soft),
        height=70,
        placeholder="Leadership, Communication, Cross-functional…",
    )


# ---- Column 2 — experience / education / projects via data_editor ---------

def _bullets_to_text(bullets: list[str]) -> str:
    return "\n".join(b or "" for b in bullets)


def _text_to_bullets(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _split_csv(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


with c2:
    st.subheader("💼 Experience")
    exp_df_rows: list[dict] = []
    for e in profile.experience:
        exp_df_rows.append(
            {
                "title": e.title or "",
                "company": e.company or "",
                "location": e.location or "",
                "start": e.start or "",
                "end": e.end or "",
            }
        )
    exp_config = {
        "title": st.column_config.TextColumn("Title"),
        "company": st.column_config.TextColumn("Company"),
        "location": st.column_config.TextColumn("Location"),
        "start": st.column_config.TextColumn("Start"),
        "end": st.column_config.TextColumn("End"),
    }
    edited_exp = st.data_editor(
        exp_df_rows,
        use_container_width=True,
        num_rows="dynamic",
        column_config=exp_config,
        hide_index=True,
        key="exp_editor",
    )

    # Bullet editors (one expander per experience row)
    bullets_per_row: list[list[str]] = []
    for i, row in enumerate(edited_exp):
        title = row.get("title") or "(untitled)"
        company = row.get("company") or "(unknown company)"
        original = (
            profile.experience[i].bullets
            if i < len(profile.experience)
            else []
        )
        with st.expander(f"📝 {title} @ {company} — bullets"):
            raw = st.text_area(
                "One achievement per line",
                value=_bullets_to_text(original),
                height=110,
                key=f"exp_bullets_{i}",
            )
        bullets_per_row.append(_text_to_bullets(raw))

    st.divider()

    st.subheader("🎓 Education")
    edu_rows: list[dict] = []
    for e in profile.education:
        edu_rows.append(
            {
                "degree": e.degree or "",
                "field": e.field or "",
                "institution": e.institution or "",
                "start": e.start or "",
                "end": e.end or "",
                "grade": e.grade or "",
            }
        )
    edited_edu = st.data_editor(
        edu_rows,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        key="edu_editor",
    )

    st.divider()

    st.subheader("🚀 Projects")
    proj_rows: list[dict] = []
    for p in profile.projects:
        proj_rows.append(
            {
                "name": p.name or "",
                "description": p.description or "",
                "tech": ", ".join(p.tech),
            }
        )
    proj_config = {
        "name": st.column_config.TextColumn("Name"),
        "description": st.column_config.TextColumn("Description"),
        "tech": st.column_config.TextColumn("Tech (comma separated)"),
    }
    edited_proj = st.data_editor(
        proj_rows,
        use_container_width=True,
        num_rows="dynamic",
        column_config=proj_config,
        hide_index=True,
        key="proj_editor",
    )

st.divider()

cc1, cc2 = st.columns(2)
with cc1:
    st.subheader("🏆 Certifications")
    certs_raw = st.text_area(
        "One per line or comma separated",
        value="\n".join(profile.certifications),
        height=90,
    )
with cc2:
    st.subheader("🌍 Languages")
    langs_raw = st.text_area(
        "One per line or comma separated",
        value="\n".join(profile.languages),
        height=90,
    )


# ---------------------------------------------------------------------------
# Save button
# ---------------------------------------------------------------------------


def _csv_or_lines_to_list(raw: str) -> list[str]:
    # Accept either commas or newlines as separators
    if "," in raw and "\n" not in raw:
        return _split_csv(raw)
    combined = [part.strip() for line in raw.splitlines() for part in line.split(",")]
    return [s for s in combined if s]


def _collect_profile_from_ui() -> Profile:
    experiences: list[ExperienceEntry] = []
    for i, row in enumerate(edited_exp):
        bullets = bullets_per_row[i] if i < len(bullets_per_row) else []
        experiences.append(
            ExperienceEntry(
                title=row.get("title") or None,
                company=row.get("company") or None,
                location=row.get("location") or None,
                start=row.get("start") or None,
                end=row.get("end") or None,
                bullets=bullets,
            )
        )
    educations: list[EducationEntry] = []
    for row in edited_edu:
        educations.append(
            EducationEntry(
                degree=row.get("degree") or None,
                field=row.get("field") or None,
                institution=row.get("institution") or None,
                start=row.get("start") or None,
                end=row.get("end") or None,
                grade=row.get("grade") or None,
            )
        )
    projects: list[ProjectEntry] = []
    for row in edited_proj:
        projects.append(
            ProjectEntry(
                name=row.get("name") or None,
                description=row.get("description") or None,
                tech=_split_csv(row.get("tech") or ""),
            )
        )

    return Profile(
        name=name or None,
        email=email or None,
        phone=phone or None,
        location=location or None,
        summary=summary or None,
        skills=SkillGroup(
            technical=_split_csv(tech_raw),
            tools=_split_csv(tools_raw),
            soft=_split_csv(soft_raw),
        ),
        experience=experiences,
        education=educations,
        projects=projects,
        certifications=_csv_or_lines_to_list(certs_raw),
        languages=_csv_or_lines_to_list(langs_raw),
    )


if st.button("💾 Save profile", type="primary"):
    try:
        new_prof = _collect_profile_from_ui()
    except ValidationError as e:
        st.error(f"❌ Invalid profile fields: {e}")
        st.stop()
    try:
        db_mod.save_profile(new_prof, raw_text=st.session_state.resume_raw_text)
    except Exception as e:  # noqa: BLE001
        st.error(f"❌ Failed to save: {e}")
    else:
        st.session_state.profile = new_prof
        st.success("✅ Profile saved!")
        st.balloons()
