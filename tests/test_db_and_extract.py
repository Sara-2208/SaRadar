"""Tests for PDF text extraction and profile DB round-trip."""
import pytest

import saradar.db as db_mod
import saradar.resume_parser as rp
from saradar.schemas import Profile, ScannedPDFError


class _FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class _FakePDF:
    def __init__(self, pages):
        self.pages = [_FakePage(t) for t in pages]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _fake_open(pages):
    return lambda _src: _FakePDF(pages)


def test_extract_text_joins_pages(monkeypatch):
    p1, p2 = "A" * 150, "B" * 150
    monkeypatch.setattr(rp.pdfplumber, "open", _fake_open([p1, p2]))
    out = rp.extract_text(b"fake")
    assert p1 in out and p2 in out


def test_extract_text_scanned_raises(monkeypatch):
    monkeypatch.setattr(rp.pdfplumber, "open", _fake_open(["short", None]))
    with pytest.raises(ScannedPDFError):
        rp.extract_text(b"fake")


def test_profile_round_trip(tmp_path):
    path = str(tmp_path / "test.db")
    db_mod.init_db(db_path=path)
    prof = Profile.model_validate({
        "name": "Jane Doe",
        "headline": "AI Engineering | Data Science",
        "links": {"github": "jane-dev"},
        "skills": {"technical": ["Python"], "tools": ["Docker"]},
        "experience": [{"title": "Data Analyst", "bullets": ["Built dashboards"]}],
        "education": [{"degree": "BSc", "bullets": ["CGPA 3.7"]}],
        "projects": [{"name": "Hackathon", "result": "Champion"}],
        "activities": [{"title": "Secretary", "bullets": ["Ran events"]}],
        "languages": ["English", "Malay"],
    })
    db_mod.save_profile(prof, raw_text="hello", db_path=path)
    loaded = db_mod.load_profile(db_path=path)
    assert loaded == prof