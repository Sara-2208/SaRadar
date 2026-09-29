"""Tests for scorer (fake embeddings, no downloads, no API calls)."""
import re

import numpy as np
import pytest

import saradar.scorer as sc
from saradar.llm import AllModelsFailed
from saradar.schemas import JobRequirements, Profile

PREFS = {"areas": ["Kuala Lumpur", "Selangor", "Putrajaya"]}

PROFILE = Profile.model_validate({
    "headline": "AI Engineering | Data Science",
    "summary": "Data science graduate skilled in machine learning and LLM integration",
    "skills": {"technical": ["Python", "SQL"], "tools": ["Docker", "PostgreSQL", "n8n"]},
    "experience": [{"title": "AI Engineer Intern", "company": "X",
                    "bullets": ["Built n8n workflows", "Deployed services using Docker"]}],
})

PROFILE_CV = Profile.model_validate({
    "skills": {"technical": ["Python"], "tools": ["LLM Integration", "Docker"]},
    "projects": [{"name": "Food Nexus",
                  "description": "CNN model for classifying banana ripening stages"}],
    "experience": [{"title": "AI Engineer Intern",
                    "bullets": ["Deployed services using Docker",
                                "Tested APIs and model endpoints"]}],
})


def _fake_embed(texts):
    """Bag-of-words vectors: same words -> similar vectors."""
    out = []
    for t in texts:
        v = np.zeros(512)
        for tok in re.findall(r"[a-z0-9]+", t.lower()):
            v[hash(tok) % 512] += 1
        n = np.linalg.norm(v)
        out.append(v / n if n else v)
    return np.array(out)


@pytest.fixture(autouse=True)
def fake_embedder(monkeypatch):
    monkeypatch.setattr(sc, "_embedder", _fake_embed)


def _req(**kw):
    base = {"title": "AI Engineer", "must_have_skills": ["Python", "Postgres", "ML", "Kubernetes"]}
    base.update(kw)
    return JobRequirements.model_validate(base)


# --- original tests --------------------------------------------------------

def test_exact_and_alias_matches():
    fit = sc.score_fit(PROFILE, _req(), preferences=PREFS)
    assert "Python" in fit.matched
    assert "Postgres" in fit.matched      # alias -> postgresql
    assert "ML" in fit.matched            # alias -> machine learning (in summary)
    assert fit.missing == ["Kubernetes"]


def test_senior_role_scores_lower():
    entry = sc.score_fit(PROFILE, _req(seniority="Entry", years_experience_min=1), preferences=PREFS)
    senior = sc.score_fit(PROFILE, _req(title="Senior AI Engineer", seniority="Senior",
                                        years_experience_min=5), preferences=PREFS)
    assert entry.score > senior.score
    assert entry.breakdown["seniority"] > senior.breakdown["seniority"]


def test_location_scores():
    kl = sc.score_fit(PROFILE, _req(location="Puchong, Selangor"), preferences=PREFS)
    sg = sc.score_fit(PROFILE, _req(location="Singapore"), preferences=PREFS)
    unknown = sc.score_fit(PROFILE, _req(), preferences=PREFS)
    remote = sc.score_fit(PROFILE, _req(location="Singapore", work_mode="Remote"), preferences=PREFS)
    assert kl.breakdown["location"] == 100
    assert sg.breakdown["location"] == 30
    assert unknown.breakdown["location"] == 70
    assert remote.breakdown["location"] == 100


def test_partial_jd_low_confidence():
    fit = sc.score_fit(PROFILE, _req(jd_quality="partial"), preferences=PREFS)
    assert fit.confidence == "low"


def test_score_in_range():
    fit = sc.score_fit(PROFILE, _req(), preferences=PREFS)
    assert 0 <= fit.score <= 100
    assert fit.label in ("Strong fit", "Fair fit", "Stretch")


def test_explain_falls_back_to_template(monkeypatch):
    def boom(*a, **k):
        raise AllModelsFailed([])
    monkeypatch.setattr(sc.llm_mod, "complete", boom)
    fit = sc.score_fit(PROFILE, _req(), preferences=PREFS)
    text = sc.explain_fit(fit, _req())
    assert str(fit.score) in text
    assert "Kubernetes" in text


# --- v2 tests ---------------------------------------------------------------

def test_related_concepts_match():
    req = _req(must_have_skills=["Computer Vision", "Generative AI", "RAG"])
    fit = sc.score_fit(PROFILE_CV, req, preferences=PREFS)
    kinds = {m.requirement: m for m in fit.must_have}
    assert kinds["Computer Vision"].kind == "similar"
    assert "CNN" in kinds["Computer Vision"].evidence
    assert kinds["Generative AI"].kind == "similar"
    assert kinds["RAG"].kind == "missing"


def test_overlap_and_related_find_deployment_and_api():
    req = _req(must_have_skills=["model deployment", "API integration"])
    fit = sc.score_fit(PROFILE_CV, req, preferences=PREFS)
    assert all(m.kind != "missing" for m in fit.must_have)


def test_label_capped_when_role_above_entry_level():
    label, note = sc._label(82, seniority_score=0.55)
    assert label == "Fair fit" and note
    label, note = sc._label(82, seniority_score=1.0)
    assert label == "Strong fit" and note is None



def test_two_year_gap_caps_score_as_stretch():
    fit = sc.score_fit(PROFILE, _req(years_experience_min=2), preferences=PREFS)
    assert fit.score <= 45
    assert fit.label == "Stretch"
    assert any("Capped" in n for n in fit.notes)