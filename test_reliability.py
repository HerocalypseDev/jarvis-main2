"""Reliability layer (2026-09-30): generic argument repair, verify-after-act receipts, the doctor."""

import json
import time

import pytest

import jarvis_doctor as doctor
import jarvis_toolargs as ta

QS = {"type": "object", "properties": {"query": {"type": "string"}, "ext": {"type": "string"},
                                      "path_prefix": {"type": "string"}, "count": {"type": "integer"}},
      "required": ["query"]}


# --- argument repair -----------------------------------------------------------------------------
def test_wrong_parameter_name_is_renamed_to_the_missing_one():
    args, notes, err = ta.check("quick_search", QS, {"name_query": "weird"})
    assert err is None and args == {"query": "weird"} and notes == ["name_query -> query"]
    args, _, err = ta.check("quick_search", QS, {"filename": "weird", "extension": "pdf"})
    assert err is None and args["query"] == "weird" and args["ext"] == "pdf"  # extension ~ ext, filename alone


def test_a_single_stray_parameter_fills_the_single_missing_required_one():
    args, notes, err = ta.check("quick_search", QS, {"needle": "weird"})
    assert err is None and args == {"query": "weird"}


def test_type_slips_and_enum_case_are_fixed():
    schema = {"type": "object", "properties": {"count": {"type": "integer"}, "on": {"type": "boolean"},
                                              "action": {"type": "string", "enum": ["list", "add"]},
                                              "tags": {"type": "array", "items": {"type": "string"}}},
              "required": ["action"]}
    args, notes, err = ta.check("t", schema, {"count": "5", "on": "yes", "action": "LIST", "tags": "a"})
    assert err is None
    assert args == {"count": 5, "on": True, "action": "list", "tags": ["a"]}


def test_unfixable_calls_return_an_error_that_teaches():
    _, _, err = ta.check("quick_search", QS, {})
    assert "needs 'query'" in err and "path_prefix" in err and "again" in err
    _, _, err = ta.check("quick_search", QS, {"colour": "red", "size": 3})  # two strays: not guessed
    assert "needs 'query'" in err and "colour" in err
    schema = {"type": "object", "properties": {"action": {"type": "string", "enum": ["list", "add"]}},
              "required": ["action"]}
    _, _, err = ta.check("t", schema, {"action": "explode"})
    assert "Valid values: list, add" in err


def test_good_calls_and_free_form_tools_pass_untouched():
    args, notes, err = ta.check("quick_search", QS, {"query": "x", "count": 3})
    assert (args, notes, err) == ({"query": "x", "count": 3}, [], None)
    assert ta.check("t", {"type": "object", "properties": {}}, {"whatever": 1})[2] is None
    assert ta.check("t", None, {"a": 1}) == ({"a": 1}, [], None)


def test_repairs_are_remembered_for_the_doctor():
    ta._recent.clear()
    ta.check("quick_search", QS, {"name_query": "a"})
    ta.check("quick_search", QS, {"name_query": "b"})
    assert "quick_search x2" in ta.summary()
    ta._recent.clear()
    assert ta.summary().startswith("no argument repairs")


# --- through the real dispatcher ----------------------------------------------------------------
@pytest.fixture()
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import jarvis as j

    monkeypatch.setattr(j, "get_mcp_tool_schemas", lambda: [])
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    j._tool_result_cache.clear()
    return j


def test_dispatcher_repairs_quick_search_arguments_and_reports_bad_calls(jarvis, monkeypatch):
    import jarvis_everything as ev
    seen = []
    monkeypatch.setattr(ev, "search", lambda q, ext="", pp="", count=25: seen.append(q) or
                        {"ok": True, "results": [{"path": "C:\\x\\weird.txt", "type": "file"}]})
    out = jarvis._execute_tool_impl("quick_search", {"name_query": "weird"}, "find weird")
    assert "weird.txt" in out and seen == ["weird"]
    out = jarvis._execute_tool_impl("quick_search", {}, "find something")
    assert out.startswith("quick_search needs 'query'")


# --- verify after acting -----------------------------------------------------------------------
def test_write_file_result_is_verified_and_a_missing_file_is_a_failure(jarvis, tmp_path, monkeypatch):
    p = tmp_path / "note.txt"
    ok = jarvis._verify_action("write_file", {"content": "hello"}, f"Wrote 5 chars to {p}.")
    assert "Tool failed" in ok and "not on disk" in ok  # nothing was written
    p.write_text("hello", encoding="utf-8")
    ok = jarvis._verify_action("write_file", {"content": "hello"}, f"Wrote 5 chars to {p}.")
    assert ok.endswith("[verified: note.txt is on disk, 5 bytes]")
    p.write_text("", encoding="utf-8")
    assert "is empty" in jarvis._verify_action("write_file", {"content": "hello"}, f"Wrote 5 chars to {p}.")
    # refusals and failures are left alone
    assert jarvis._verify_action("write_file", {}, "Refused: that path is protected.") == "Refused: that path is protected."
    assert jarvis._verify_action("write_file", {}, "No path given.") == "No path given."


def test_reminder_and_fact_are_read_back_from_the_database(jarvis):
    out = jarvis._execute_tool_impl("create_reminder", {"text": "call mum", "due_in_minutes": 30}, "remind me")
    assert out.startswith("Reminder set") and "[verified: reminder #" in out
    out = jarvis._execute_tool_impl("remember_fact", {"category": "fact", "content": "likes tea"}, "remember")
    assert "[verified: stored as fact #" in out
    # the claim checker counts a verification failure as a failed tool
    assert jarvis._looks_failed("Tool failed: the reminder was not saved. Reminder set for 10:00: x.")


def test_prompt_tells_the_model_to_rely_on_verified_results(jarvis):
    text = " ".join(b.get("text", "") for b in jarvis.build_system_blocks(""))
    assert "[verified: ...]" in text and "read the page back" in text


# --- doctor --------------------------------------------------------------------------------------
def test_google_login_warns_when_the_same_sign_in_is_about_a_week_old(tmp_path, monkeypatch):
    cred = tmp_path / "credentials.json"
    cred.write_text(json.dumps({"refresh_token": "1//abc", "access_token": "x"}), encoding="utf-8")
    monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", str(cred))
    monkeypatch.setenv("GOOGLE_CALENDAR_MCP_TOKEN_PATH", str(tmp_path / "none.json"))
    monkeypatch.setattr(doctor.Path, "home", staticmethod(lambda: tmp_path))  # no real calendar tokens
    state: dict = {}
    day = 86400.0
    now = 1_000_000_000.0
    assert doctor.google_login_checks(now, state)[0]["status"] == "ok"           # first seen today
    assert doctor.google_login_checks(now + 3 * day, state)[0]["status"] == "ok"
    warn = doctor.google_login_checks(now + 6.5 * day, state)[0]
    assert warn["status"] == "warn" and "npx.cmd @gongrzhe/server-gmail-autoauth-mcp auth" in warn["fix"]
    cred.write_text(json.dumps({"refresh_token": "1//NEW", "access_token": "y"}), encoding="utf-8")  # signed in again
    assert doctor.google_login_checks(now + 7 * day, state)[0]["status"] == "ok"
    assert "1//" not in json.dumps(state)  # only a fingerprint is ever stored


def test_run_checks_reports_missing_keys_and_speaks_the_problems(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(doctor, "ROOT", tmp_path)
    monkeypatch.setattr(doctor.Path, "home", staticmethod(lambda: tmp_path))
    import jarvis_everything as ev
    monkeypatch.setattr(ev, "reachable", lambda *a, **k: False)
    checks = doctor.run_checks(env={"JARVIS_LLM_PROVIDER": "gemini"})
    names = {c["name"]: c for c in checks}
    assert names["Brain key"]["status"] == "fail" and "GEMINI_API_KEY" in names["Brain key"]["fix"]
    assert names["File search (Everything)"]["status"] == "warn"
    said = doctor.speech(checks)
    assert "Brain key" in said and "Fix:" in said
    ok = doctor.run_checks(env={"JARVIS_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "k"})
    assert {c["name"]: c for c in ok}["Brain key"]["status"] == "ok"


def test_a_switched_on_feature_with_a_missing_package_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(doctor.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(doctor, "_has", lambda m: m != "openwakeword")
    import jarvis_everything as ev
    monkeypatch.setattr(ev, "reachable", lambda *a, **k: True)
    checks = doctor.run_checks(env={"ANTHROPIC_API_KEY": "k", "JARVIS_WAKE_WORD": "1"})
    pk = {c["name"]: c for c in checks}["Python packages"]
    assert pk["status"] == "warn" and "openwakeword" in pk["detail"]


def test_health_card_and_self_check_include_doctor_problems(jarvis, monkeypatch):
    fake = [{"name": "Gmail sign-in", "status": "warn", "detail": "signed in 6 days ago", "fix": "Run the auth command"}]
    monkeypatch.setattr(jarvis.doctor, "run_checks", lambda *a, **k: fake)
    monkeypatch.setattr(jarvis.doctor, "problems", lambda *a, **k: fake)
    items = {i["name"]: i for i in jarvis.health_report()["items"]}
    assert items["Gmail sign-in"]["ok"] is False and "Fix: Run the auth command" in items["Gmail sign-in"]["detail"]


def test_google_expiry_notice_fires_once_per_half_day(jarvis, monkeypatch):
    sent = []
    monkeypatch.setattr(jarvis, "queue_or_deliver_notification", lambda t, **k: sent.append(t))
    jarvis._google_reauth_told.clear()
    jarvis._notify_google_reauth("gmail")
    jarvis._notify_google_reauth("gmail")
    jarvis._notify_google_reauth("calendar")
    assert len(sent) == 2 and "npx.cmd @gongrzhe/server-gmail-autoauth-mcp auth" in sent[0]
    jarvis._google_reauth_told["gmail"] = time.time() - 13 * 3600
    jarvis._notify_google_reauth("gmail")
    assert len(sent) == 3


def test_doctor_tick_announces_each_problem_once(jarvis, monkeypatch):
    sent = []
    monkeypatch.setattr(jarvis, "queue_or_deliver_notification", lambda t, **k: sent.append(t))
    bad = [{"name": "File search (Everything)", "status": "warn", "detail": "not answering", "fix": "Enable HTTP server"}]
    monkeypatch.setattr(jarvis.doctor, "problems", lambda *a, **k: bad)
    jarvis._doctor_state.update(next=0.0, told={}, force=True)
    jarvis._doctor_tick()
    jarvis._doctor_state["next"] = 0.0  # twelve hours later
    jarvis._doctor_tick()
    assert len(sent) == 1 and "Enable HTTP server" in sent[0]
    jarvis._doctor_state["force"] = False


# --- eval drafts and capped eval runs ---------------------------------------------------------
def _seed_debug_db(path):
    import sqlite3
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE dashboard_sessions (started_at TEXT, source TEXT, transcript TEXT, status TEXT, "
                 "reply TEXT, ended_at TEXT)")
    conn.execute("CREATE TABLE action_audit (id INTEGER PRIMARY KEY, timestamp TEXT, tool_name TEXT, tool_input TEXT, "
                 "result TEXT, transcript TEXT)")
    rows = [("2026-09-30T10:21:07", "dashboard", "find the file called weird", "done", "I couldn't find any file named weird", None),
            ("2026-09-30T10:30:00", "voice", "what time is it", "done", "It is 10:30.", None),
            ("2026-09-30T10:40:00", "voice", "open notes", "done", "Opened.", None),
            ("2026-09-30T10:42:00", "voice", "open notes", "done", "Opened.", None)]
    conn.executemany("INSERT INTO dashboard_sessions VALUES (?,?,?,?,?,?)", rows)
    conn.executemany("INSERT INTO action_audit (timestamp, tool_name, tool_input, result, transcript) VALUES (?,?,?,?,?)",
                     [("2026-09-30T10:21:10", "quick_search", '{"name_query": "weird"}', "Say what to search for.",
                       "find the file called weird"),
                      ("2026-09-30T10:22:17", "run_shell", '{"command": "gci"}', "exit_code=0", "find the file called weird"),
                      ("2026-09-30T10:30:01", "system_status", "{}", "ok", "what time is it")])
    conn.commit()
    conn.close()


def test_debug_report_drafts_evals_from_failures_repeats_and_apologies(tmp_path):
    import sys
    from datetime import datetime
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent / "tools"))
    import collect_debug as cd
    db = tmp_path / "m.db"
    _seed_debug_db(db)
    drafts = cd.build_eval_drafts(24, now=datetime(2026, 9, 30, 12, 0), db=db)
    said = {d["say"]: d for d in drafts}
    assert set(said) == {"find the file called weird", "open notes"}  # the plain "what time is it" is not a failure
    weird = said["find the file called weird"]
    assert weird["id"] == "draft-find-the-file-called-weird" and "quick_search" in weird["why"]
    assert weird["expect_any"] == [{"tool": "run_shell"}] and "cases.json" in weird["_review"]
    assert "repeat" in said["open notes"]["why"]


def test_capped_eval_runs_rotate_through_all_cases():
    import jarvis_eval as je
    cases = [{"id": str(i)} for i in range(10)]
    seen = set()
    for day in range(4):
        picked = je.pick_rotating(cases, 3, day)
        assert len(picked) == 3
        seen |= {c["id"] for c in picked}
    assert seen == {str(i) for i in range(10)}
