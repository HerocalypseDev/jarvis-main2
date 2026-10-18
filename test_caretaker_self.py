"""Caretaker phase 3: Jarvis fixing its own repeated failures (skills, tool servers, jobs, agents).
Pure planner + classifier first, then the jarvis.py wiring with everything faked (no real skill or server runs)."""
import os
import sqlite3
from datetime import datetime, timedelta

import pytest

import jarvis_caretaker as ct
import jarvis_caretaker_probe as probe


# --- explaining an error -------------------------------------------------------------------------
@pytest.mark.parametrize("error,kind,retry", [
    ("invalid_grant: Token has been expired or revoked", "auth", False),
    ("Your credit balance is too low to access the API", "credit", False),
    ("429 RESOURCE_EXHAUSTED daily limit", "quota", False),
    ("getaddrinfo failed", "network", True),
    ("couldn't reach Claude", "network", True),
    ("Tool failed: mcp_gmail_search_emails needs 'query'", "tool", False),
    ("(nothing to report)", "other", True),
    ("", "other", True),
])
def test_explain_failure_kinds(error, kind, retry):
    r = ct.explain_failure(error)
    assert r["kind"] == kind and r["retry"] is retry and r["advice"]


def test_a_finding_carries_its_cause_and_advice():
    f = ct.self_failure_finding("skill", "gmail_watch", "invalid_grant", 3)
    assert f.evidence["cause"] == "auth" and "sign in" in f.evidence["advice"]


# --- store helpers -------------------------------------------------------------------------------
@pytest.fixture()
def store(tmp_path):
    path = tmp_path / "s.db"
    return ct.Store(lambda: sqlite3.connect(path))


def test_give_up_keeps_the_attempt_count_and_the_reason(store):
    store.ingest([ct.self_failure_finding("skill", "x", "invalid_grant", 3)])
    store.give_up("self_skill:x", "sign in again")
    i = store.get("self_skill:x")
    assert i["status"] == "gave_up" and i["attempts"] == 0 and i["tried"] == ["sign in again"]
    assert store.open_issues() == [] and [v["key"] for v in store.visible_issues()] == ["self_skill:x"]


def test_last_action_is_the_newest_one_for_that_issue_and_kind(store):
    assert store.last_action("k", "rerun_skill") is None
    store.log_action("k", ct.GREEN, "rerun_skill", "first", "started")
    store.log_action("k", ct.GREEN, "rerun_skill", "second", "started")
    store.log_action("k", ct.GREEN, "reconnect_mcp", "other kind", "connected")
    store.log_action("other", ct.GREEN, "rerun_skill", "other issue", "started")
    assert store.last_action("k", "rerun_skill")["detail"] == "second"


# --- the planner ---------------------------------------------------------------------------------
NOW = datetime(2026, 10, 16, 12, 0, 0)


def _iss(kind, name, error, count=3):
    f = ct.self_failure_finding(kind, name, error, count)
    return {"key": f.key, "category": f.category, "evidence": f.evidence, "title": f.title}


def _try(minutes_ago):
    return {"ts": (NOW - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")}


def test_a_job_is_never_run_again_by_the_caretaker():
    p = ct.plan_self_fix(_iss("job", "send the report", "getaddrinfo failed"), None, NOW)
    assert p["do"] == "give_up" and "won't run it again" in p["why"]


def test_an_agent_waits_for_its_own_schedule_unless_the_cause_needs_the_owner():
    assert ct.plan_self_fix(_iss("agent", "a", "getaddrinfo failed"), None, NOW)["do"] == "none"
    assert ct.plan_self_fix(_iss("agent", "a", "(x)"), None, NOW)["do"] == "none"
    assert ct.plan_self_fix(_iss("agent", "a", "invalid_grant"), None, NOW)["do"] == "give_up"
    assert ct.plan_self_fix(_iss("agent", "a", "Tool failed: needs 'q'"), None, NOW)["do"] == "give_up"


def test_a_tool_server_is_reconnected_but_not_every_minute():
    i = _iss("mcp", "gmail", "could not connect", 1)
    assert ct.plan_self_fix(i, None, NOW)["do"] == "reconnect_mcp"
    assert ct.plan_self_fix(i, _try(2), NOW)["do"] == "wait"
    assert ct.plan_self_fix(i, _try(9), NOW)["do"] == "reconnect_mcp"


def test_a_skill_failing_for_a_reason_retrying_cannot_fix_is_not_re_run():
    for err in ("invalid_grant", "credit balance is too low", "Tool failed: needs 'query'"):
        assert ct.plan_self_fix(_iss("skill", "s", err), None, NOW)["do"] == "give_up"
    assert ct.plan_self_fix(_iss("skill", "s", "429 daily limit"), None, NOW)["do"] == "wait"


def test_a_skill_is_re_run_at_most_every_thirty_minutes_and_a_failed_rerun_counts():
    i = _iss("skill", "s", "getaddrinfo failed")
    assert ct.plan_self_fix(i, None, NOW) == {"do": "rerun_skill", "why": "", "count_failed": False}
    assert ct.plan_self_fix(i, _try(10), NOW)["do"] == "wait"
    again = ct.plan_self_fix(i, _try(40), NOW)
    assert again["do"] == "rerun_skill" and again["count_failed"] is True
    # an earlier episode (a day ago) is not a failed attempt of this one
    assert ct.plan_self_fix(i, _try(24 * 60), NOW)["count_failed"] is False


def test_doctor_findings_and_crashes_are_page_only():
    d = ct.self_failure_finding("doctor", "Google sign-in", "expires soon", 1)
    assert ct.plan_self_fix({"key": d.key, "category": d.category, "evidence": d.evidence}, None, NOW)["do"] == "none"


# --- the agent sensor ----------------------------------------------------------------------------
def test_probe_self_reports_an_enabled_agent_whose_last_run_failed(tmp_path):
    db = tmp_path / "a.db"

    def connect():
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE IF NOT EXISTS background_agents (name TEXT, enabled INTEGER, last_ok INTEGER, "
                  "last_result TEXT)")
        return c

    c = connect()
    c.executemany("INSERT INTO background_agents VALUES (?,?,?,?)", [
        ("invoice_watch", 1, 0, "Tool failed: mcp_gmail_search_emails needs 'query'"),
        ("paused_one", 0, 0, "boom"), ("fine_one", 1, 1, "ok")])
    c.commit(); c.close()
    out = probe.probe_self(connect)
    assert [f.key for f in out] == ["self_agent:invoice_watch"] and out[0].evidence["cause"] == "tool"


# --- wiring in jarvis.py -------------------------------------------------------------------------
@pytest.fixture()
def jv(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "jv.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import jarvis as j
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(j, "_caretaker_store", ct.Store(j._memory_db_connect))
    monkeypatch.setattr(j, "_caretaker_state", {"check": 0.0, "running": False, "last": None, "announced": set()})
    monkeypatch.setattr(j.doctor, "problems", lambda *a, **k: [])
    monkeypatch.setattr(j.autonomy, "hard_disabled", lambda: False)
    said = []
    monkeypatch.setattr(j, "queue_or_deliver_notification", lambda t, **kw: said.append((t, kw)))
    monkeypatch.setattr(j, "alert_owner", lambda t, level="important", key=None, source="": said.append((t, {"level": level, "important": level != "minor", "urgent": level == "urgent"})))
    j._said = said
    return j


def _open(jv, kind, name, error, count=3):
    jv._caretaker_store.ingest([ct.self_failure_finding(kind, name, error, count)])
    return f"self_{kind}:{name.lower()}"


def _age_actions(jv, key, minutes):
    ts = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    c = jv._memory_db_connect()
    with c:
        c.execute("UPDATE caretaker_actions SET ts=? WHERE issue_key=?", (ts, key))


@pytest.fixture()
def skills(jv, monkeypatch):
    runs = []
    monkeypatch.setattr(jv, "_load_skills", lambda: [{"name": "gmail_watch", "instructions": "x"},
                                                      {"name": "weekly_report", "instructions": "y"}])
    monkeypatch.setattr(jv, "_skills_off", lambda: set())
    monkeypatch.setattr(jv, "_run_single_flight", lambda name, fn, *a: runs.append((name, a[0]["name"])) or True)
    return runs


def test_a_skill_failing_on_a_sign_in_is_not_re_run_and_the_owner_is_told_once(jv, skills):
    key = _open(jv, "skill", "gmail_watch", "invalid_grant")
    jv._caretaker_fix_all()
    jv._caretaker_fix_all()
    assert skills == []
    assert jv._caretaker_store.get(key)["status"] == "gave_up"
    assert len(jv._said) == 1 and "sign in again" in jv._said[0][0]
    # 2026-10-18: a give-up reaches the owner (Telegram + said before their next command), never as an urgent call
    assert jv._said[0][1]["level"] == "important"


def test_a_failing_skill_is_re_run_then_counted_then_given_up_after_three(jv, skills):
    key = _open(jv, "skill", "gmail_watch", "(nothing to report)")
    assert jv._caretaker_fix_all() == ["ran the gmail_watch skill again"]
    assert skills == [("skill:gmail_watch", "gmail_watch")]
    assert jv._caretaker_fix_all() == []            # too soon: nothing, and no attempt counted
    assert jv._caretaker_store.get(key)["attempts"] == 0
    for expected_attempts in (1, 2):                # each later pass: the last re-run didn't help
        _age_actions(jv, key, 40)
        assert jv._caretaker_fix_all() == ["ran the gmail_watch skill again"]
        assert jv._caretaker_store.get(key)["attempts"] == expected_attempts
    _age_actions(jv, key, 40)
    assert jv._caretaker_fix_all() == []            # third failed attempt -> give up, no fourth run
    assert len(skills) == 3 and jv._caretaker_store.get(key)["status"] == "gave_up"
    assert len(jv._said) == 1 and "kept failing" in jv._said[0][0]


def test_a_skill_that_works_after_the_re_run_closes_as_fixed(jv, skills, monkeypatch):
    key = _open(jv, "skill", "gmail_watch", "getaddrinfo failed")
    monkeypatch.setattr(jv.caretaker_probe, "run_all",
                        lambda **k: (k["report"].__setitem__("ok", {"self"}) or []))   # the sensor now sees no failure
    jv._caretaker_fix_all()
    jv._caretaker_run()
    assert jv._caretaker_store.get(key)["status"] == "fixed"
    assert not any("couldn't fix" in t for t, _ in jv._said)


def test_a_brain_outage_does_not_re_run_every_skill_at_once(jv, skills):
    for n in ("a", "b", "c", "d"):
        _open(jv, "skill", n, "couldn't reach Claude")
    monkeypatch_skills = [{"name": n} for n in ("a", "b", "c", "d")]
    jv._load_skills = lambda: monkeypatch_skills
    done = jv._caretaker_fix_all()
    assert len(done) == jv.CARETAKER_RERUNS_PER_PASS == len(skills)


def test_a_daily_limit_just_waits(jv, skills):
    key = _open(jv, "skill", "gmail_watch", "429 RESOURCE_EXHAUSTED daily limit")
    assert jv._caretaker_fix_all() == [] and skills == [] and jv._said == []
    assert jv._caretaker_store.get(key)["status"] == "open" and jv._caretaker_store.get(key)["attempts"] == 0


def test_a_switched_off_or_deleted_skill_is_dropped_without_a_word(jv, skills, monkeypatch):
    key = _open(jv, "skill", "billing_watch", "(nothing to report)")
    jv._caretaker_fix_all()
    assert skills == [] and jv._said == [] and jv._caretaker_store.get(key)["status"] == "gave_up"
    key2 = _open(jv, "skill", "gmail_watch", "(nothing to report)")
    monkeypatch.setattr(jv, "_skills_off", lambda: {"gmail_watch"})
    jv._caretaker_fix_all()
    assert skills == [] and jv._said == [] and jv._caretaker_store.get(key2)["status"] == "gave_up"


def test_a_failed_job_is_explained_never_re_run(jv, skills, monkeypatch):
    ran = []
    monkeypatch.setattr(jv, "_deferred_tick", lambda *a, **k: ran.append(1), raising=False)
    key = _open(jv, "job", "send the weekly report", "getaddrinfo failed", count=2)
    jv._caretaker_fix_all()
    assert skills == [] and ran == [] and jv._caretaker_store.get(key)["status"] == "gave_up"
    assert "won't run it again" in jv._said[0][0]


def test_nothing_is_re_run_in_safe_mode_or_with_fixes_off(jv, skills, monkeypatch):
    _open(jv, "skill", "gmail_watch", "(nothing to report)")
    monkeypatch.setattr(jv.autonomy, "hard_disabled",
                        lambda: (os.environ.get("JARVIS_SAFE_MODE") or "") == "1")   # the fixture stubs it off
    monkeypatch.setenv("JARVIS_SAFE_MODE", "1")
    assert jv._caretaker_fix_all() == [] and skills == []
    monkeypatch.delenv("JARVIS_SAFE_MODE")
    monkeypatch.setenv("JARVIS_CARETAKER_ACT", "0")
    assert jv._caretaker_fix_all() == [] and skills == []


def test_the_hourly_action_budget_stops_re_runs(jv, skills):
    for i in range(ct.MAX_ACTIONS_PER_HOUR):
        jv._caretaker_store.log_action("x", ct.GREEN, "noop", "d", "r")
    _open(jv, "skill", "gmail_watch", "(nothing to report)")
    assert jv._caretaker_fix_all() == [] and skills == []


def test_a_down_tool_server_is_reconnected_and_the_issue_closes(jv, monkeypatch):
    monkeypatch.setitem(jv._mcp_failed_servers, "gmail", {"cfg": {}, "last_attempt": datetime.now()})
    retried = []
    monkeypatch.setattr(jv, "_retry_failed_mcp_servers",
                        lambda now: (retried.append(now), jv._mcp_failed_servers.pop("gmail", None)))
    key = _open(jv, "mcp", "gmail", "could not connect", count=1)
    assert jv._caretaker_fix_all() == ["reconnected the gmail tool server"]
    assert retried and jv._caretaker_store.get(key)["status"] == "fixed"
    assert jv._caretaker_store.recent_actions(5)[0]["action"] == "reconnect_mcp"


def test_a_server_that_stays_down_is_given_up_with_the_sign_in_command(jv, monkeypatch):
    monkeypatch.setitem(jv._mcp_failed_servers, "gmail", {"cfg": {}, "last_attempt": datetime.now()})
    monkeypatch.setattr(jv, "_retry_failed_mcp_servers", lambda now: None)   # never recovers
    key = _open(jv, "mcp", "gmail", "could not connect", count=1)
    for _ in range(3):
        jv._caretaker_fix_all()
        _age_actions(jv, key, 10)
    i = jv._caretaker_store.get(key)
    assert i["status"] == "gave_up" and i["attempts"] == 3
    assert len(jv._said) == 1 and "auth" in jv._said[0][0]


def test_an_agent_with_a_broken_step_is_explained_and_left_alone(jv):
    key = _open(jv, "agent", "invoice_watch", "Tool failed: mcp_gmail_search_emails needs 'query'", count=2)
    jv._caretaker_fix_all()
    assert jv._caretaker_store.get(key)["status"] == "gave_up" and "has to be rewritten" in jv._said[0][0]


def test_the_status_line_says_what_only_the_owner_can_do(jv, skills):
    _open(jv, "skill", "gmail_watch", "invalid_grant")
    jv._caretaker_fix_all()
    out = jv._caretaker_tool({"action": "status"})
    assert "needs you" in out and "sign in again" in out and "gave up after" not in out
