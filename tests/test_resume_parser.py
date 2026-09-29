"""Tests for resume_parser v2: references removal, masking, 2 passes, smart retry."""
import saradar.resume_parser as rp
from saradar.llm import LLMResult

SAMPLE = """JANE DOE
Email: jane@gmail.com Phone: 012-345 6789
WORK EXPERIENCE
Data Analyst - ABC Sdn Bhd Jan 2024 - Present
- Built dashboards
EDUCATION
BSc Data Science, UMS
LEADERSHIP & ACTIVITIES
Secretary, Tech Club
REFERENCES
Dr. Ref - ref@uni.edu.my - 019-888 7777
"""


def _res(model: str) -> LLMResult:
    return LLMResult(text="{}", model_used=model, attempts=[])


def test_strip_references_removes_referees():
    out = rp._strip_references(SAMPLE)
    assert "ref@uni.edu.my" not in out
    assert "Dr. Ref" not in out
    assert "EDUCATION" in out


def test_third_party_contacts_masked_only_own_restored(monkeypatch):
    prompts = []

    def fake(prompt, system=None, tier="fast"):
        prompts.append(prompt)
        if "PASS B" in system:
            return {"education": [{"degree": "BSc Data Science"}],
                    "activities": [{"title": "Secretary"}]}, _res("fake/fast")
        return {"name": "JANE DOE", "email": "[EMAIL]", "phone": "[PHONE]",
                "experience": [{"title": "Data Analyst"}]}, _res("fake/fast")

    monkeypatch.setattr(rp.llm_mod, "complete_json", fake)
    # Rename heading so the 3rd-party contact stays in the text
    text = SAMPLE.replace("REFERENCES", "OTHER CONTACTS")
    outcome = rp.parse_resume_full(text)

    for p in prompts:
        assert "jane@gmail.com" not in p
        assert "ref@uni.edu.my" not in p
        assert "019-888 7777" not in p
    assert outcome.profile.email == "jane@gmail.com"
    assert outcome.profile.phone == "012-345 6789"


def test_two_passes_merge(monkeypatch):
    def fake(prompt, system=None, tier="fast"):
        if "PASS B" in system:
            return {"education": [{"degree": "BSc"}],
                    "activities": [{"title": "Secretary"}]}, _res("fake/b")
        return {"name": "JANE", "experience": [{"title": "Data Analyst"}]}, _res("fake/a")

    monkeypatch.setattr(rp.llm_mod, "complete_json", fake)
    outcome = rp.parse_resume_full(SAMPLE)
    assert outcome.profile.name == "JANE"
    assert outcome.profile.experience[0].title == "Data Analyst"
    assert outcome.profile.education[0].degree == "BSc"
    assert outcome.profile.activities[0].title == "Secretary"
    assert outcome.warnings == []


def test_completeness_retry_uses_smart_tier(monkeypatch):
    calls = []

    def fake(prompt, system=None, tier="fast"):
        is_b = "PASS B" in system
        calls.append((is_b, tier))
        if is_b and tier == "fast":
            return {"education": [], "activities": []}, _res("fake/fast")
        if is_b:
            return {"education": [{"degree": "BSc"}],
                    "activities": [{"title": "Secretary"}]}, _res("fake/smart")
        return {"name": "JANE", "experience": [{"title": "Data Analyst"}]}, _res("fake/fast")

    monkeypatch.setattr(rp.llm_mod, "complete_json", fake)
    outcome = rp.parse_resume_full(SAMPLE)
    assert (True, "smart") in calls
    assert outcome.profile.education[0].degree == "BSc"
    assert outcome.warnings == []
    assert "fake/smart" in outcome.models_used


def test_warning_when_section_still_missing(monkeypatch):
    def fake(prompt, system=None, tier="fast"):
        if "PASS B" in system:
            return {"education": [], "activities": [{"title": "Secretary"}]}, _res("fake")
        return {"name": "JANE", "experience": [{"title": "Data Analyst"}]}, _res("fake")

    monkeypatch.setattr(rp.llm_mod, "complete_json", fake)
    outcome = rp.parse_resume_full(SAMPLE)
    assert any("Education" in w for w in outcome.warnings)