"""Tests for pipeline (mocked extractor + scorer)."""
import json

import saradar.pipeline as pl
from saradar import job_store
from saradar.jobs import normalize
from saradar.schemas import JobRequirements, Profile
from saradar.scorer import FitResult

PROFILE = Profile.model_validate({"name": "Test", "skills": {"technical": ["Python"]}})


def _raw(title, company):
    return {"job_title": title, "employer_name": company, "job_city": "Kuala Lumpur",
            "job_state": "Selangor", "job_description": "We need Python. " * 50}


def test_score_unscored_saves_and_ranks(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    job_store.upsert_jobs([normalize(_raw("AI Engineer", "A")),
                           normalize(_raw("Data Scientist", "B"))], db_path=db)

    def fake_extract(text, title=None, company=None, location=None):
        return JobRequirements(title=title, company=company, location=location,
                               must_have_skills=["Python"]), None

    def fake_score(profile, req, jd_text=None, preferences=None):
        score = 80 if req.company == "A" else 40
        return FitResult(score=score, label="Strong fit" if score > 75 else "Stretch",
                         breakdown={}, must_have=[], nice_to_have=[], confidence="high")

    monkeypatch.setattr(pl, "extract_requirements", fake_extract)
    monkeypatch.setattr(pl, "score_fit", fake_score)

    rep = pl.score_unscored(profile=PROFILE, db_path=db)
    assert len(rep.scored) == 2 and not rep.failed

    ranked = job_store.list_jobs(db_path=db)
    assert [j["company"] for j in ranked] == ["A", "B"]      # best fit first
    assert json.loads(ranked[0]["fit_json"])["score"] == 80

    rep2 = pl.score_unscored(profile=PROFILE, db_path=db)      # already scored
    assert rep2.scored == []


def test_one_failure_does_not_stop_others(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    job_store.upsert_jobs([normalize(_raw("AI Engineer", "A")),
                           normalize(_raw("Data Scientist", "B"))], db_path=db)

    def flaky(text, title=None, company=None, location=None):
        if company == "A":
            raise RuntimeError("boom")
        return JobRequirements(title=title, company=company), None

    monkeypatch.setattr(pl, "extract_requirements", flaky)
    monkeypatch.setattr(pl, "score_fit", lambda *a, **k: FitResult(
        50, "Fair fit", {}, [], [], "high"))
    rep = pl.score_unscored(profile=PROFILE, db_path=db)
    assert len(rep.scored) == 1 and len(rep.failed) == 1