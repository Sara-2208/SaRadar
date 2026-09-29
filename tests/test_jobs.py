"""Tests for jobs + job_store (no network)."""
import saradar.jobs as jobs
from saradar import job_store

PREFS = {
    "areas": ["Kuala Lumpur", "Selangor", "Putrajaya"],
    "max_distance_km": 40,
    "skip_title_keywords": ["intern", "senior manager", "leader"],
    "job_search": {"queries": ["q1", "q2"], "monthly_budget": 180},
}


def raw(title, company="Acme", city="Kuala Lumpur", state="Federal Territory of Kuala Lumpur",
        lat=3.13, lng=101.68, desc="x" * 50, remote=False):
    return {"job_title": title, "employer_name": company, "job_city": city, "job_state": state,
            "job_latitude": lat, "job_longitude": lng, "job_description": desc,
            "job_is_remote": remote, "job_apply_link": "https://example.com", "job_publisher": "Test"}


def test_filters():
    keep = jobs.normalize(raw("AI Engineer"))
    intern = jobs.normalize(raw("Applied AI Engineer-Intern"))
    senior_mgr = jobs.normalize(raw("Senior Manager - AI Engineer"))
    chef = jobs.normalize(raw("Head Chef"))
    sg = jobs.normalize(raw("Data Scientist", city="Singapore", state="Singapore", lat=1.35, lng=103.8))
    seri = jobs.normalize(raw("AI Engineer", city="Seri Kembangan", state="Selangor", lat=3.02, lng=101.70))
    far_no_state = jobs.normalize(raw("AI Engineer", city="Ipoh", state="Perak", lat=4.6, lng=101.09))
    remote = jobs.normalize(raw("Data Analyst", city=None, state=None, lat=None, lng=None, remote=True))

    assert jobs.filter_reason(keep, PREFS) is None
    assert "intern" in jobs.filter_reason(intern, PREFS)
    assert "senior manager" in jobs.filter_reason(senior_mgr, PREFS)
    assert jobs.filter_reason(chef, PREFS) == "title not relevant"
    assert "outside area" in jobs.filter_reason(sg, PREFS)
    assert jobs.filter_reason(seri, PREFS) is None
    assert "outside area" in jobs.filter_reason(far_no_state, PREFS)
    assert jobs.filter_reason(remote, PREFS) is None


def test_dedupe_keeps_longest():
    a = jobs.normalize(raw("AI Engineer: GenAI, ML", company="Artefact", desc="short"))
    b = jobs.normalize(raw("AI Engineer: GenAI, ML & Cloud Solutions", company="Artefact", desc="much longer text"))
    out = jobs.dedupe([a, b])
    assert len(out) == 1 and out[0].description == "much longer text"


def test_store_new_then_seen(tmp_path):
    db = str(tmp_path / "t.db")
    j = jobs.normalize(raw("AI Engineer", company="Artefact"))
    assert len(job_store.upsert_jobs([j], db_path=db)) == 1
    assert len(job_store.upsert_jobs([j], db_path=db)) == 0
    twin = jobs.normalize(raw("AI Engineer - GenAI", company="Artefact"))
    assert len(job_store.upsert_jobs([twin], db_path=db)) == 0   # near-duplicate


def test_run_search_counts_usage_and_respects_budget(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    calls = []

    def fake_search(query, cfg, key):
        calls.append(query)
        return [raw("AI Engineer", company=f"Co{len(calls)}"), raw("Head Chef")]

    monkeypatch.setattr(jobs, "_search", fake_search)
    monkeypatch.setattr(jobs, "get_api_key", lambda name: "fake-key")

    rep = jobs.run_search(preferences=PREFS, db_path=db)
    assert rep.requests_used == 2
    assert len(rep.new) == 2
    assert job_store.get_usage("jsearch", db_path=db) == 2

    job_store.add_usage("jsearch", n=178, db_path=db)  # now at 180 = budget
    rep2 = jobs.run_search(preferences=PREFS, db_path=db)
    assert rep2.requests_used == 0
    assert any("budget" in m for m in rep2.messages)


def test_dry_run_makes_no_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_search", lambda *a: (_ for _ in ()).throw(AssertionError("called")))
    rep = jobs.run_search(preferences=PREFS, dry_run=True, db_path=str(tmp_path / "t.db"))
    assert rep.requests_used == 0