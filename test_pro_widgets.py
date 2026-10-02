"""Jarvis4U Pro Home widgets: spec validation, computations, key gating, and the route behind the dashboard guard."""
import base64
import json
from datetime import date, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import jarvis_license as lic
import jarvis_pro as pro
import jarvis_pro_widgets as w

TODAY = date(2026, 10, 2)


def test_specs_keep_only_known_types_sources_and_plain_text():
    ok, why = pro.validate_widget({"id": "exams", "title": "Exams", "type": "countdown", "source": "facts",
                                   "prefix": "Exam:", "limit": 99, "html": "<script>x</script>", "sql": "1; DROP"})
    assert why == "" and ok == {"id": "exams", "title": "Exams", "type": "countdown", "source": "facts",
                                "limit": 20, "prefix": "Exam:"}
    bad = [
        {"id": "Bad Id", "title": "t", "type": "list", "source": "reminders"},
        {"id": "x", "title": "<b>hi</b>", "type": "list", "source": "reminders"},
        {"id": "x", "title": "t", "type": "iframe", "source": "reminders"},
        {"id": "x", "title": "t", "type": "list", "source": "files"},
        {"id": "x", "title": "t", "type": "list", "source": "facts"},                       # facts need a prefix
        {"id": "x", "title": "t", "type": "list", "source": "facts", "prefix": "%' OR 1=1 --"},
        {"id": "x", "title": "t", "type": "list", "source": "reminders", "limit": "lots"},
        "not an object",
    ]
    for spec in bad:
        assert pro.validate_widget(spec)[0] is None, spec


def test_countdown_skips_past_dates_and_sorts_soonest_first():
    lines = ["Exam: Chemistry on 2026-11-03 09:00", "Exam: Maths on 2026-10-05", "Exam: History on 2026-09-01",
             "Exam: Maths on 2026-10-05"]
    out = w.compute({"id": "e", "title": "E", "type": "countdown", "source": "facts", "prefix": "Exam:", "limit": 5},
                    lines, TODAY)
    assert out["items"] == [{"label": "Maths", "date": "2026-10-05", "days": 3},
                            {"label": "Chemistry", "date": "2026-11-03", "days": 32}]
    assert not out["empty"]


def test_score_trend_turns_scores_into_percentages_per_subject():
    lines = ["Exam score: Physics 14/20 on 2026-10-02 (weak: projectile motion, units)",   # newest first, like the DB
             "Exam score: Physics 9/20 on 2026-09-28 (weak: units)",
             "Exam score: Chemistry 30/40 on 2026-09-30",
             "Exam score: garbage line"]
    out = w.compute({"id": "s", "title": "S", "type": "score_trend", "source": "facts", "prefix": "Exam score:",
                     "limit": 5}, lines, TODAY)
    phys = next(s for s in out["subjects"] if s["subject"] == "Physics")
    assert phys["points"] == [45, 70] and phys["latest"] == 70 and phys["first"] == 45 and phys["sessions"] == 2
    assert phys["weak"] == "projectile motion, units"
    assert [s["subject"] for s in out["subjects"]] == ["Physics", "Chemistry"]


def test_board_groups_by_status_and_the_newest_line_wins():
    lines = ["Job application: Flutterwave / Junior QA / applied 2026-09-20 / status interview",
             "Job application: Paystack / Support / applied 2026-09-25 / status applied",
             "Job application: Flutterwave / Junior QA / applied 2026-09-20 / status applied"]
    out = w.compute({"id": "j", "title": "J", "type": "board", "source": "facts", "prefix": "Job application:",
                     "limit": 6}, lines, TODAY)
    assert out["columns"] == [{"status": "applied", "items": ["Paystack · Support"], "count": 1},
                              {"status": "interview", "items": ["Flutterwave · Junior QA"], "count": 1}]


def test_stat_list_and_empty_widgets():
    stat = w.compute({"id": "st", "title": "Streak", "type": "stat", "source": "facts", "prefix": "Study streak:"},
                     ["Study streak: 4 days, last 2026-10-02"], TODAY)
    assert stat["value"] == 4 and stat["caption"] == "4 days, last 2026-10-02"
    rem = w.compute({"id": "r", "title": "R", "type": "list", "source": "reminders", "limit": 1},
                    [("Gym time.", "2026-10-02T18:00:00"), ("Read.", "2026-10-02T22:00:00")], TODAY)
    assert rem["items"] == [{"label": "Gym time.", "when": "2026-10-02 18:00"}]
    empty = w.compute({"id": "e", "title": "E", "type": "countdown", "source": "facts", "prefix": "Exam:"}, [], TODAY)
    assert empty["empty"]


@pytest.fixture()
def pro_on(monkeypatch, tmp_path):
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(lic, "PUBLIC_KEY_B64", base64.urlsafe_b64encode(raw).rstrip(b"=").decode())
    monkeypatch.setattr(lic, "REVOKED_IDS", frozenset())
    key = lic.sign({"e": "a@b.c", "t": "pro", "i": "2026-10-02", "n": "w1"}, private)
    pack = tmp_path / "pro"
    (pack / "widgets").mkdir(parents=True)
    (pack / "manifest.json").write_text(json.dumps({"name": "Jarvis4U Pro", "version": "9.9.9"}))
    (pack / "widgets" / "home.json").write_text(json.dumps([
        {"id": "exams", "title": "Exams", "type": "countdown", "source": "facts", "prefix": "Exam:"},
        {"id": "broken", "title": "x", "type": "script", "source": "facts", "prefix": "Exam:"},
        {"id": "upcoming", "title": "Coming up", "type": "list", "source": "reminders"},
        {"id": "meetings", "title": "Meetings", "type": "list", "source": "meetings"},
    ]))
    monkeypatch.setenv("JARVIS_PRO_DIR", str(pack))
    monkeypatch.setenv(lic.ENV_KEY, key)
    return key


@pytest.fixture()
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import jarvis as j
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    return j


def test_route_is_off_without_a_key(jarvis, monkeypatch):
    monkeypatch.delenv(lic.ENV_KEY, raising=False)
    assert jarvis._FEATURE_PROVIDERS["pro_widgets"]("get", {}) == {"active": False, "widgets": []}


def test_route_computes_widgets_from_the_users_own_rows_and_skips_bad_specs(jarvis, pro_on):
    soon = (datetime.now().date() + timedelta(days=5)).isoformat()
    jarvis.remember_fact("goal", f"Exam: Physics on {soon} 09:00", key="exam:physics")
    jarvis.remember_fact("goal", "Not an exam line", key="other")
    out = jarvis._FEATURE_PROVIDERS["pro_widgets"]("get", {})
    assert out["active"] and [x["id"] for x in out["widgets"]] == ["exams", "upcoming", "meetings"]
    exams = out["widgets"][0]
    assert exams["items"] == [{"label": "Physics", "date": soon, "days": 5}]
    assert out["widgets"][1]["empty"] and out["widgets"][2]["empty"]   # no reminders; meetings table may not exist


def test_route_sits_behind_the_dashboard_host_guard(jarvis, pro_on):
    import importlib

    import jarvis_dashboard as d
    importlib.reload(d)
    d.providers["feature:pro_widgets"] = jarvis._FEATURE_PROVIDERS["pro_widgets"]
    from fastapi.testclient import TestClient
    with TestClient(d._build_app(), base_url="http://127.0.0.1:8765", raise_server_exceptions=False) as c:
        assert c.get("/api/feature/pro_widgets").json()["active"] is True
        assert c.post("/api/feature/pro_widgets/delete", json={}).status_code >= 400   # read-only
    with TestClient(d._build_app(), base_url="http://evil.example.com") as c:
        assert c.get("/api/feature/pro_widgets").status_code == 403


def test_board_labels_skip_bare_dates():
    out = w.compute({"id": "c", "title": "C", "type": "board", "source": "facts", "prefix": "Content plan:", "limit": 6},
                    ["Content plan: 2026-10-03 / TikTok / how I prep for JAMB / status idea"], TODAY)
    assert out["columns"] == [{"status": "idea", "items": ["TikTok · how I prep for JAMB"], "count": 1}]
