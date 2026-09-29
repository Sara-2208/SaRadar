"""Tests for requirements_extractor (mocked LLM)."""
import saradar.requirements_extractor as rx
from saradar.llm import LLMResult

LONG_JD = "We are hiring an AI Engineer. " * 40  # > 600 chars


def _fake(returns):
    def fake(prompt, system=None, tier="fast"):
        return returns, LLMResult(text="{}", model_used="fake/model", attempts=[])
    return fake


def test_years_parsed_and_skills_deduped(monkeypatch):
    monkeypatch.setattr(rx.llm_mod, "complete_json", _fake({
        "title": "AI Engineer",
        "years_experience_min": "3-5 years",
        "must_have_skills": ["Python", "python", "SQL"],
        "nice_to_have_skills": ["SQL", "Docker"],
    }))
    req, res = rx.extract_requirements(LONG_JD)
    assert req.years_experience_min == 3
    assert req.must_have_skills == ["Python", "SQL"]
    assert req.nice_to_have_skills == ["Docker"]  # SQL already a must-have
    assert req.jd_quality == "full"
    assert res.model_used == "fake/model"


def test_known_metadata_wins(monkeypatch):
    monkeypatch.setattr(rx.llm_mod, "complete_json", _fake({
        "title": "Wrong Title", "company": "Wrong Co", "location": None,
    }))
    req, _ = rx.extract_requirements(LONG_JD, title="AI Engineer", company="Artefact",
                                     location="Kuala Lumpur")
    assert req.title == "AI Engineer"
    assert req.company == "Artefact"
    assert req.location == "Kuala Lumpur"


def test_short_jd_marked_partial(monkeypatch):
    monkeypatch.setattr(rx.llm_mod, "complete_json", _fake({"must_have_skills": "Python, SQL"}))
    req, _ = rx.extract_requirements("Short summary JD for an AI role in KL.")
    assert req.jd_quality == "partial"
    assert req.must_have_skills == ["Python", "SQL"]  # comma string -> list


def test_empty_jd_raises():
    import pytest
    with pytest.raises(ValueError):
        rx.extract_requirements("   ")