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


# --- parallel read-only tools -------------------------------------------------------------------
def test_read_only_tools_in_one_turn_run_together_and_keep_their_order(jarvis, monkeypatch):
    import threading
    started, ctx_seen = [], []
    barrier = threading.Barrier(2, timeout=5)  # both must be running at the same moment

    def fake_execute(name, inp, transcript, skip_confirmation=False):
        ctx_seen.append(getattr(jarvis._command_ctx, "source", None))
        started.append(name)
        barrier.wait()
        return f"result of {name}"

    monkeypatch.setattr(jarvis, "_execute_tool", fake_execute)
    jarvis._command_ctx.source = "voice"
    uses = [{"id": "a", "name": "weather", "input": {}}, {"id": "b", "name": "run_shell", "input": {"command": "x"}},
            {"id": "c", "name": "system_status", "input": {}}]
    out = jarvis._run_read_only_tools_parallel(uses, "how is everything")
    assert out == {0: "result of weather", 2: "result of system_status"}  # run_shell (index 1) is left to the loop
    assert set(started) == {"weather", "system_status"} and ctx_seen == ["voice", "voice"]  # context copied to workers


def test_one_read_only_tool_or_the_off_switch_means_no_parallel_run(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_execute_tool", lambda *a, **k: "x")
    assert jarvis._run_read_only_tools_parallel([{"name": "weather", "input": {}}], "t") == {}
    two = [{"name": "weather", "input": {}}, {"name": "system_status", "input": {}}]
    monkeypatch.setenv("JARVIS_PARALLEL_TOOLS", "0")
    assert jarvis._run_read_only_tools_parallel(two, "t") == {}
    monkeypatch.setenv("JARVIS_PARALLEL_TOOLS", "1")
    assert set(jarvis._run_read_only_tools_parallel(two, "t")) == {0, 1}


def test_a_crashing_parallel_tool_becomes_a_failed_result_not_a_lost_turn(jarvis, monkeypatch):
    def fake(name, inp, transcript, skip_confirmation=False):
        if name == "weather":
            raise RuntimeError("boom")
        return "fine"

    monkeypatch.setattr(jarvis, "_execute_tool", fake)
    out = jarvis._run_read_only_tools_parallel(
        [{"name": "weather", "input": {}}, {"name": "system_status", "input": {}}], "t")
    assert out[0].startswith("Tool failed") and out[1] == "fine"


def test_agent_loop_feeds_parallel_results_back_in_the_models_order(jarvis, monkeypatch):
    calls = []
    monkeypatch.setattr(jarvis, "_execute_tool",
                        lambda name, inp, transcript, skip_confirmation=False: calls.append(name) or f"R:{name}")
    monkeypatch.setattr(jarvis, "_llm_provider", lambda: "claude")
    monkeypatch.setattr(jarvis, "_history_snapshot", lambda: [])
    monkeypatch.setattr(jarvis, "_append_history", lambda *a, **k: None)
    monkeypatch.setattr(jarvis, "_spawn_lesson", lambda *a: None)
    sent = []
    rounds = iter([
        {"content": [{"type": "tool_use", "id": "t1", "name": "weather", "input": {}},
                     {"type": "tool_use", "id": "t2", "name": "system_status", "input": {}}],
         "stop_reason": "tool_use", "usage": {}},
        {"content": [{"type": "text", "text": "Sunny and fine."}], "stop_reason": "end_turn", "usage": {}},
    ])

    def fake_request(body, timeout=None):
        sent.append(body["messages"][-1])
        return next(rounds)

    monkeypatch.setattr(jarvis, "_claude_request", fake_request)
    reply = jarvis.run_agent_loop("weather and system status")
    assert reply == "Sunny and fine." and sorted(calls) == ["system_status", "weather"]
    results = sent[-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]
    assert [r["content"] for r in results] == ["R:weather", "R:system_status"]


# --- prompt diet: a budget so it cannot quietly grow again --------------------------------------------
def test_narrowed_request_stays_inside_the_token_budget(jarvis):
    """What a Gemini/Ollama round carries every time: system prompt + the narrowed tool list. Measured 2026-09-30:
    ~5.1k + ~4.5k tokens. This fails when a change adds a lot more, so bloat is a decision, not an accident."""
    import jarvis_tool_router as R
    system_chars = sum(len(b.get("text", "")) for b in jarvis.build_system_blocks("", "find the file weird"))
    for say in ("find the file called weird on my laptop", "fill the form on my screen",
                "set a reminder to call mum in 10 minutes"):
        tools = R.select(say, jarvis.AGENT_TOOLS, limit=jarvis.TOOL_NARROWING_LIMIT, core=jarvis._narrowing_core(say))
        tool_chars = len(json.dumps(tools))
        assert tool_chars < 24_000, f"narrowed tool schemas grew to ~{tool_chars // 4} tokens for {say!r}"
    assert system_chars < 28_000, f"system prompt grew to ~{system_chars // 4} tokens"
    assert len(jarvis.AGENT_TOOLS) < 130, "too many tools: retire or merge some (each costs tokens every round)"


def test_usage_summary_reports_average_prompt_size_per_call(tmp_path):
    import sqlite3
    import threading
    import jarvis_billing as b
    conn = sqlite3.connect(tmp_path / "u.db")
    b._ensure_usage_table(conn)
    now = time.time()
    for i in range(2):
        conn.execute("INSERT INTO api_usage (ts, model, input_tokens, cache_read_tokens, cache_write_tokens, "
                     "output_tokens, cost_usd, saved_usd) VALUES (?,?,?,?,?,?,?,?)",
                     (now, "m", 1000 + 1000 * i, 500, 0, 50, 0.001, 0.0))
    conn.commit()
    conn.close()
    s = b.local_summary(lambda: sqlite3.connect(tmp_path / "u.db"), threading.Lock(), now)
    assert s["periods"]["today"]["calls"] == 2 and s["periods"]["today"]["avg_prompt_tokens"] == 2000


# --- tool registry sanity: what a single per-tool record would guarantee ---------------------------
def test_tool_registry_is_consistent(jarvis):
    import inspect
    import re as _re
    tools = jarvis.AGENT_TOOLS
    names = [t["name"] for t in tools]
    assert len(names) == len(set(names)), "duplicate tool names"
    for t in tools:
        assert len(t.get("description", "")) >= 25, f"{t['name']} needs a real description (models pick tools by it)"
        sch = t.get("input_schema") or {}
        assert sch.get("type") == "object", f"{t['name']} schema must be an object"
        for r in sch.get("required", []):
            assert r in (sch.get("properties") or {}), f"{t['name']} requires {r!r} but has no such property"
    known = set(names)
    # every place that names tools must name real ones
    assert set(jarvis.READONLY_TOOL_TTLS) <= known, set(jarvis.READONLY_TOOL_TTLS) - known
    import jarvis_tool_router as R
    assert set(R.CORE_TOOLS) <= known, set(R.CORE_TOOLS) - known
    assert set(jarvis._VERIFIED_TOOLS) <= known
    assert {n for n in jarvis.SCREEN_KIT_TOOLS if not n.startswith("mcp_")} <= known
    assert set(jarvis._BATCH_TOOL_HANDLERS) <= known, set(jarvis._BATCH_TOOL_HANDLERS) - known
    # read-only means read-only: nothing that writes may sit in the parallel/cached list
    writes = _re.compile(r"^(write|create|delete|send|run|type|click|set|save|forget|remember|cancel|queue|start|"
                         r"open|play|download|enroll|approve|resume)")
    assert not [n for n in jarvis.READONLY_TOOL_TTLS if writes.match(n)]
    # every built-in tool is dispatched somewhere
    src = inspect.getsource(jarvis._execute_tool_impl)
    unhandled = [n for n in names if f'"{n}"' not in src and n not in jarvis._BATCH_TOOL_HANDLERS
                 and n != jarvis.tool_router.FIND_TOOLS_NAME]
    assert not unhandled, f"tools with no dispatch branch: {unhandled}"


def test_announcement_lines_only_name_real_tools(jarvis):
    known = {t["name"] for t in jarvis.AGENT_TOOLS}
    for n in ("quick_search", "web_search", "delegate_to_claude_code", "change_jarvis_code", "delegate_research",
              "review_code", "code_search", "briefing", "write_file", "read_file", "download_image", "read_screen",
              "type_text", "click_at", "scroll_screen", "run_shell", "run_python"):
        assert n in known, f"_tool_announcement talks about {n!r}, which is not a tool any more"
        assert jarvis._tool_announcement(n, {}) is not None


# --- macro suggestions ------------------------------------------------------------------------------
def _macro_db(tmp_path):
    import sqlite3
    import threading
    path = tmp_path / "m.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE dashboard_sessions (started_at TEXT, source TEXT, transcript TEXT, status TEXT, "
                 "reply TEXT, ended_at TEXT)")
    conn.execute("CREATE TABLE action_audit (id INTEGER PRIMARY KEY, timestamp TEXT, tool_name TEXT, tool_input TEXT, "
                 "result TEXT, transcript TEXT)")
    conn.close()
    return path, (lambda: sqlite3.connect(path)), threading.Lock()


def _say(path, when, text, tool, inp, result="ok"):
    import sqlite3
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO dashboard_sessions VALUES (?,?,?,?,?,?)", (when, "voice", text, "done", "", None))
    conn.execute("INSERT INTO action_audit (timestamp, tool_name, tool_input, result, transcript) VALUES (?,?,?,?,?)",
                 (when, tool, json.dumps(inp), result, text))
    conn.commit()
    conn.close()


def test_habits_become_macro_suggestions_but_only_with_low_risk_tools(tmp_path):
    from datetime import datetime, timedelta
    import jarvis_macros as m
    path, connect, lock = _macro_db(tmp_path)
    now = datetime(2026, 9, 30, 12, 0)
    for i in range(4):
        when = (now - timedelta(days=i)).isoformat(timespec="seconds")
        _say(path, when, "start my study setup", "open_app", {"app": "notes"})
        _say(path, when, "email sam the report", "mcp_gmail_send_email", {"to": "sam"})     # never suggested
        _say(path, when, "how is the system", "system_status", {})
    _say(path, now.isoformat(timespec="seconds"), "one off command here", "weather", {})      # said once: no habit
    safe = m.PACK_ALLOWED_TOOLS
    known = safe | {"mcp_gmail_send_email"}
    out = m.suggest(connect, lock, safe, known, already_fast=lambda p: False, now=now)
    phrases = {s["phrase"] for s in out}
    assert phrases == {"start my study setup", "how is the system"}
    study = next(s for s in out if s["phrase"] == "start my study setup")
    assert study["steps"] == [{"tool": "open_app", "input": {"app": "notes"}}] and study["count"] == 4
    # things Jarvis already answers instantly, and phrases already taken, are not suggested
    assert not m.suggest(connect, lock, safe, known, already_fast=lambda p: p == "how is the system", now=now) \
        or "how is the system" not in {s["phrase"] for s in m.suggest(connect, lock, safe, known,
                                                                      already_fast=lambda p: p == "how is the system", now=now)}


def test_a_failing_or_unstable_habit_is_not_suggested_and_accept_needs_the_pc(tmp_path):
    from datetime import datetime, timedelta
    import jarvis_macros as m
    path, connect, lock = _macro_db(tmp_path)
    now = datetime(2026, 9, 30, 12, 0)
    for i in range(4):
        when = (now - timedelta(hours=i)).isoformat(timespec="seconds")
        _say(path, when, "open my notes please", "open_app", {"app": "notes"}, result="Tool failed: nope")
        _say(path, when, "start focus time now", "open_app", {"app": "notes" if i % 2 else "vscode"})  # not the same call
    safe = m.PACK_ALLOWED_TOOLS
    assert m.suggest(connect, lock, safe, safe, now=now) == []
    for i in range(3):
        _say(path, (now - timedelta(minutes=i)).isoformat(timespec="seconds"), "open my notes app", "open_app",
             {"app": "notes"})
    tool = lambda act, attended, **kw: m.handle_tool(connect, lock, dict(action=act, **kw), safe, attended,
                                                     safe_tools=safe, already_fast=None)
    assert "open my notes app" in tool("suggest", True)
    assert tool("accept", False, phrase="open my notes app").startswith("Macros can only be changed")
    assert tool("accept", True, phrase="something else").startswith("That isn't one of the current suggestions")
    assert tool("accept", True, phrase="open my notes app").startswith("Saved macro")
    assert m.match(connect, lock, "open my notes app")["steps"][0]["tool"] == "open_app"
    assert "open my notes app" not in tool("suggest", True)  # now a macro: not suggested again


# --- plans that a restart cut short can be resumed -----------------------------------------------------
def _plan(jarvis, statuses):
    task_id = jarvis._insert_background_task("do the four things", "plan", "[]")
    with jarvis._memory_db_lock:
        conn = jarvis._memory_db_connect()
        for i, st in enumerate(statuses):
            conn.execute("INSERT INTO plan_steps (task_id, step_index, description, depends_on, status, created_at, "
                         "result_summary) VALUES (?,?,?,?,?,?,?)",
                         (task_id, i, f"step {i}", "[]", st, "2026-09-30T10:00:00", f"result {i}" if st == "done" else None))
        conn.commit()
        conn.close()
    return task_id


def test_interrupted_plan_resumes_from_the_first_unfinished_step(jarvis, monkeypatch):
    ran = []
    monkeypatch.setattr(jarvis, "_run_plan_step", lambda desc, ctx: ran.append((desc, ctx)) or f"did {desc}")
    monkeypatch.setattr(jarvis, "_finish_background_task", lambda tid, status, summary, kind="": ran.append(("finish", status, summary)))
    monkeypatch.setattr(jarvis, "record_recent_task", lambda *a: None)
    task_id = _plan(jarvis, ["done", "done", "pending", "pending"])
    jarvis._recover_interrupted_background_tasks()
    with jarvis._memory_db_lock:
        conn = jarvis._memory_db_connect()
        conn.execute("UPDATE background_tasks SET status='failed', result_summary='interrupted by a Jarvis restart' "
                     "WHERE id=?", (task_id,))
        conn.commit()
        conn.close()
    msg = jarvis._resume_plan(task_id)
    assert "2 of 4 steps were already done" in msg
    import time as _t
    for _ in range(100):
        if any(r[0] == "finish" for r in ran):
            break
        _t.sleep(0.02)
    assert [r[0] for r in ran if r[0] != "finish"] == ["step 2", "step 3"]  # finished steps are not run again
    assert ran[-1][:2] == ("finish", "done") and "step 0: result 0" in ran[-1][2]
    assert "already running" in jarvis._resume_plan(task_id)  # (the stubbed finish left the row 'running')
    assert jarvis._resume_plan(99999).startswith("There is no plan")
    assert jarvis._resume_plan("x").startswith("Give the plan's number")


def test_restart_notice_names_the_cut_short_plan_once(jarvis, monkeypatch):
    sent = []
    monkeypatch.setattr(jarvis, "queue_or_deliver_notification", lambda t, **k: sent.append(t))
    task_id = _plan(jarvis, ["done", "pending", "pending"])
    with jarvis._memory_db_lock:
        conn = jarvis._memory_db_connect()
        conn.execute("UPDATE background_tasks SET status='failed', result_summary='interrupted by a Jarvis restart', "
                     "finished_at=? WHERE id=?", (jarvis.datetime.now().isoformat(timespec="seconds"), task_id))
        conn.commit()
        conn.close()
    jarvis._interrupted_told.update(done=False, force=True)
    jarvis._interrupted_plans_tick()
    jarvis._interrupted_plans_tick()
    jarvis._interrupted_told["force"] = False
    assert len(sent) == 1 and f"resume plan {task_id}" in sent[0] and "1 of 3 steps done" in sent[0]


def test_set_plan_schema_lets_a_resume_call_through_the_argument_check(jarvis):
    sch = next(t for t in jarvis.AGENT_TOOLS if t["name"] == "set_plan")["input_schema"]
    assert "resume_task_id" in sch["properties"] and not sch.get("required")
    args, notes, err = ta.check("set_plan", sch, {"resume_task_id": "7"})
    assert err is None and args["resume_task_id"] == 7


def test_toolbox_endpoint_lists_habit_suggestions_and_accept_creates_the_macro(jarvis, monkeypatch, tmp_path):
    from datetime import datetime, timedelta
    from fastapi.testclient import TestClient
    import jarvis_dashboard as dash
    monkeypatch.setattr(jarvis, "_log_action_audit", lambda *a, **k: None)
    now = datetime.now()
    dash._connect().close()  # creates the dashboard's own tables in the temp DB
    with jarvis._memory_db_lock:
        conn = jarvis._memory_db_connect()
        for i in range(3):
            when = (now - timedelta(hours=i + 1)).isoformat(timespec="seconds")
            conn.execute("INSERT INTO dashboard_sessions (started_at, source, transcript, status, reply) "
                         "VALUES (?,?,?,?,?)", (when, "voice", "start my study setup", "done", ""))
            conn.execute("INSERT INTO action_audit (timestamp, transcript, tool_name, tool_input, result) "
                         "VALUES (?,?,?,?,?)", (when, "start my study setup", "open_app", '{"app": "notepad"}', "Opened notepad."))
        conn.commit()
        conn.close()
    monkeypatch.setattr(jarvis, "_macro_known_tools", lambda: {"open_app", "weather"})
    with TestClient(dash._build_app(), base_url="http://127.0.0.1:8765") as c:
        data = c.get("/api/feature/macros").json()
        assert [s["phrase"] for s in data["suggestions"]] == ["start my study setup"]
        assert data["suggestions"][0]["steps"] == [{"tool": "open_app", "input": {"app": "notepad"}}]
        r = c.post("/api/feature/macros/accept", json={"phrase": "start my study setup"}).json()
        assert r["result"].startswith("Saved macro")
        again = c.get("/api/feature/macros").json()
        assert again["suggestions"] == [] and [m["name"] for m in again["macros"]] == ["start_my_study_setup"]
