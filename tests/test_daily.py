"""Tests for notify + daily loop (no network)."""
import saradar.daily as daily
from saradar import job_store
from saradar.jobs import normalize
from saradar.notify import TELEGRAM_LIMIT, build_digest
from saradar.pipeline import ScoreReport


def _job(title, fit, label="Fair fit", url="https://x.com/job"):
    return {"hash": title, "title": title, "company": "Co", "city": "Kuala Lumpur",
            "fit": fit, "fit_label": label, "url": url, "jd_status": "full"}


def test_digest_sorts_filters_and_counts():
    msgs = build_digest([_job("B", 60), _job("A", 80, "Strong fit"), _job("C", 30, "Stretch")],
                        min_fit=50)
    assert len(msgs) == 1
    text = msgs[0]
    assert text.index("80%") < text.index("60%")
    assert "🔴" not in text                           # stretch job (below min) not listed
    assert "+1 below 50%" in text


def test_digest_empty_when_nothing_above_min():
    assert build_digest([_job("C", 30, "Stretch")], min_fit=50) == []


def test_digest_escapes_html_and_splits_long():
    jobs = [_job(f"R&D Engineer {i} " + "x" * 120, 70) for i in range(60)]
    msgs = build_digest(jobs, min_fit=50)
    assert len(msgs) > 1
    assert all(len(m) <= TELEGRAM_LIMIT for m in msgs)
    assert "R&amp;D" in msgs[0]


def test_max_jobs_limits_list():
    msgs = build_digest([_job(str(i), 60 + i) for i in range(10)], min_fit=50, max_jobs=3)
    assert "+7 more" in msgs[0]


def _seed(db):
    raws = [{"job_title": t, "employer_name": c, "job_city": "Kuala Lumpur",
             "job_description": "x" * 700} for t, c in [("AI Engineer", "A"), ("Data Analyst", "B")]]
    jobs = [normalize(r) for r in raws]
    job_store.upsert_jobs(jobs, db_path=db)
    job_store.save_fit(jobs[0].hash, "{}", "{}", 80, "Strong fit", db_path=db)
    job_store.save_fit(jobs[1].hash, "{}", "{}", 40, "Stretch", db_path=db)


def test_run_daily_sends_once(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    _seed(db)
    sent = []
    monkeypatch.setattr(daily, "send_telegram", lambda text: sent.append(text))
    monkeypatch.setattr(daily, "score_unscored", lambda **k: ScoreReport())
    prefs = {"notify": {"min_fit": 50}}

    preview = daily.run_daily(do_search=False, dry_run=True, preferences=prefs, db_path=db)
    assert preview.messages and sent == []                    # dry run sends nothing

    rep = daily.run_daily(do_search=False, preferences=prefs, db_path=db)
    assert rep.sent == 1 and rep.notified == 2
    assert "AI Engineer" in sent[0] and "+1 below 50%" in sent[0]

    rep2 = daily.run_daily(do_search=False, preferences=prefs, db_path=db)
    assert rep2.sent == 0                                     # nothing new