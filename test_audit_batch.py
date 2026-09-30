"""Audit of the 2026-09-30 feature batch (wake word, Everything, announcements, reliability layer, speed layer,
product feel, self-awareness): one regression test per defect found."""

import json
import sqlite3
import threading
import time

import numpy as np
import pytest

import jarvis_toolargs as ta


@pytest.fixture()
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import jarvis as j
    monkeypatch.setattr(j, "get_mcp_tool_schemas", lambda: [])
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    j._tool_result_cache.clear()
    return j


# --- A. wake word: a wake capture can never confirm a staged action ---------------------------------------------
def test_a_wake_word_capture_saying_yes_never_approves_a_staged_shutdown(jarvis, monkeypatch):
    said, ran = [], []
    monkeypatch.setattr(jarvis, "speak_text", lambda t: said.append(t))
    monkeypatch.setattr(jarvis, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(jarvis, "transcribe_pcm", lambda *a, **k: "Hey Jarvis, yes")
    monkeypatch.setattr(jarvis, "_execute_confirmed_action", lambda *a, **k: ran.append(a))
    monkeypatch.setattr(jarvis, "_pending_action", {"tool_name": "run_shell", "tool_input": {"command": "shutdown /s /t 0"},
                                                    "queued_at": time.monotonic()})
    jarvis._handle_voice_command_impl(np.ones(16000, dtype=np.float32), 16000, hands_free=True, wake=True)
    assert ran == [] and jarvis._pending_action is not None and "push-to-talk" in said[-1]


def test_wake_word_is_off_by_default_and_a_bad_threshold_cannot_crash(monkeypatch):
    import jarvis_wakeword as w
    monkeypatch.delenv("JARVIS_WAKE_WORD", raising=False)
    assert not w.enabled()
    monkeypatch.setenv("JARVIS_WAKE_THRESHOLD", "loud")
    assert w.threshold() == w.DEFAULT_THRESHOLD


# --- B. Everything -----------------------------------------------------------------------------------------------
def test_es_exe_gets_the_query_as_one_argument_so_backslashes_and_apostrophes_survive(monkeypatch):
    import subprocess
    import jarvis_everything as ev
    seen = []

    class P:
        returncode, stdout = 0, "C:\\Users\\x\\Documents\\don't stop.txt\n"

    monkeypatch.setattr(ev, "_http", lambda *a, **k: (_ for _ in ()).throw(OSError("no http server")))
    monkeypatch.setenv("JARVIS_EVERYTHING_ES", "es.exe")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: seen.append(cmd) or P())
    r = ev.search("don't stop", path_prefix="C:\\Users\\x\\Documents\\")
    assert r["ok"] and r["backend"] == "es" and r["results"][0]["path"].endswith("don't stop.txt")
    assert seen[0][-1] == '"C:\\Users\\x\\Documents\\" don\'t stop' and len(seen[0]) == 6


def test_a_non_numeric_count_falls_back_instead_of_raising(monkeypatch):
    import jarvis_everything as ev
    monkeypatch.setattr(ev, "_http", lambda url, q, count: [{"path": "C:\\a.txt", "type": "file"}])
    assert ev.search("a", count="lots")["ok"]


# --- C. announcements --------------------------------------------------------------------------------------------
def test_no_announcement_is_made_for_a_command_the_gate_will_stage(jarvis):
    assert jarvis._tool_announcement("run_shell", {"command": "dir"}) == "Sure, I'll run that on your PC now."
    assert jarvis._tool_announcement("run_shell", {"command": "shutdown /s /t 0"}) is None
    assert jarvis._tool_announcement("mcp_windows_Type", {"text": "shutdown /s /t 0"}) is None


# --- D. argument repair never guesses into something that changes the call ---------------------------------------
SEND = {"type": "object", "properties": {"to": {"type": "string"}, "cc": {"type": "string"}, "body": {"type": "string"},
                                         "force": {"type": "boolean"}, "text_color": {"type": "string"},
                                         "message": {"type": "string"}}, "required": ["to", "body"]}


def test_a_similar_name_is_never_guessed_into_an_optional_or_risky_parameter():
    args, notes, err = ta.check("send", SEND, {"to": "a", "body": "b", "cc_address": "evil@x.y", "forced": True})
    assert err is None and "cc" not in args and "force" not in args
    assert "ignored unknown: cc_address, forced" in notes
    args, _, _ = ta.check("t", SEND, {"to": "a", "body": "b", "text": "red"})
    assert "text_color" not in args
    # the safe repairs still work: a required parameter under another name, and an abbreviation
    args, notes, err = ta.check("send", SEND, {"recipients": "a", "body": "b"})
    assert err is None and args["to"] == "a"
    qs = {"type": "object", "properties": {"query": {"type": "string"}, "ext": {"type": "string"}}, "required": ["query"]}
    assert ta.check("qs", qs, {"name_query": "w", "extension": "pdf"})[0] == {"query": "w", "ext": "pdf"}


def test_a_repaired_shell_call_still_goes_through_the_gate(jarvis):
    out = jarvis._execute_tool("run_shell", {"cmd": "shutdown /s /t 0"}, "shut down")
    assert "staged, not run" in out and jarvis._pending_action is not None
    jarvis._take_pending_action()


# --- E. verify-after-act -----------------------------------------------------------------------------------------
def test_a_saved_file_with_dots_and_spaces_in_its_name_is_verified_not_reported_missing(jarvis, tmp_path):
    f = tmp_path / "notes v1.2 draft.txt"
    f.write_text("hello")
    out = jarvis._verify_action("write_file", {"content": "hello"}, f"Wrote 5 bytes to {f}.")
    assert "[verified: notes v1.2 draft.txt is on disk" in out and not out.startswith("Tool failed")
    gone = tmp_path / "missing v2.0 file.txt"
    assert jarvis._verify_action("write_file", {"content": "x"}, f"Wrote 1 bytes to {gone}.").startswith("Tool failed")


# --- F. doctor ---------------------------------------------------------------------------------------------------
def test_doctor_announces_a_problem_once_by_name_and_never_the_developer_note(jarvis, monkeypatch):
    said = []
    monkeypatch.setattr(jarvis, "queue_or_deliver_notification", lambda m, **k: said.append(m))
    problems = [{"name": "Gmail sign-in", "status": "warn", "detail": "signed in 6 days ago", "fix": "run auth"},
                {"name": "Tool arguments", "status": "warn", "detail": "argument repairs: x x2", "fix": "", "quiet": True}]
    monkeypatch.setattr(jarvis.doctor, "problems", lambda *a, **k: problems)
    jarvis._doctor_state.update({"force": True, "next": 0.0, "told": {}})
    try:
        jarvis._doctor_tick()
        problems[0] = {**problems[0], "detail": "signed in 7 days ago"}  # tomorrow's wording of the same problem
        jarvis._doctor_state["next"] = 0.0
        jarvis._doctor_tick()
        assert len(said) == 1 and "Gmail sign-in" in said[0] and not any("Tool arguments" in m for m in said)
        jarvis._doctor_state["told"]["Gmail sign-in"] = time.time() - 4 * 86400  # still broken 4 days later: remind
        jarvis._doctor_state["next"] = 0.0
        jarvis._doctor_tick()
        assert len(said) == 2
        problems.clear()  # fixed: forgotten, so a recurrence is news again
        jarvis._doctor_state["next"] = 0.0
        jarvis._doctor_tick()
        assert jarvis._doctor_state["told"] == {}
    finally:
        jarvis._doctor_state.update({"force": False, "next": 0.0, "told": {}})


def test_doctor_state_is_written_atomically_and_holds_no_token(tmp_path, monkeypatch):
    import jarvis_doctor as d
    monkeypatch.setattr(d, "STATE_PATH", tmp_path / "doctor_state.json")
    tok = tmp_path / "credentials.json"
    tok.write_text(json.dumps({"refresh_token": "1//super-secret-refresh-token"}))
    monkeypatch.setattr(d, "_google_token_paths", lambda server: [tok] if server == "gmail" else [])
    d.google_login_checks()
    raw = (tmp_path / "doctor_state.json").read_text()
    assert "super-secret" not in raw and json.loads(raw)["google_login"]["gmail"]["fp"]
    assert not (tmp_path / "doctor_state.tmp").exists()


# --- G. parallel read-only tools ---------------------------------------------------------------------------------
def test_only_read_only_tools_run_in_parallel_and_each_branch_has_its_own_command_context(jarvis, monkeypatch):
    seen = {}

    def fake(name, inp, transcript, skip_confirmation=False):
        seen[name] = (threading.current_thread().name, getattr(jarvis._command_ctx, "source", None))
        jarvis._command_ctx.source = "changed-in-worker"   # must not leak to the caller or a sibling
        return f"R:{name}"

    monkeypatch.setattr(jarvis, "_execute_tool", fake)
    jarvis._command_ctx.source = "voice"
    tus = [{"name": "write_file", "input": {}}, {"name": "weather", "input": {}}, {"name": "run_shell", "input": {}},
           {"name": "system_status", "input": {}}]
    out = jarvis._run_read_only_tools_parallel(tus, "t")
    assert set(out) == {1, 3}, "writes, shell and sends are never run in parallel"
    assert seen["weather"][1] == "voice" and seen["system_status"][1] == "voice"
    assert seen["weather"][0].startswith("jarvis-tool") and jarvis._command_ctx.source == "voice"


def test_no_parallel_tool_can_write_send_or_run_code(jarvis):
    risky = ("write", "send", "delete", "run_", "type", "click", "create", "set_", "remember", "forget", "restart", "email",
             "shell", "python", "delegate", "open_url", "open_app", "play", "download", "install", "kill", "close", "move")
    assert not [n for n in jarvis.READONLY_TOOL_TTLS if any(r in n for r in risky)]
    assert not [n for n in jarvis.READONLY_TOOL_TTLS if n.startswith("mcp_")]


# --- I. product feel ---------------------------------------------------------------------------------------------
def test_habit_macros_never_come_from_information_tools_whose_answer_would_become_done(tmp_path):
    import jarvis_macros as m
    from datetime import datetime, timedelta
    db = tmp_path / "m.db"
    connect, lock = (lambda: sqlite3.connect(str(db))), threading.Lock()
    conn = connect()
    conn.execute("CREATE TABLE dashboard_sessions (id INTEGER PRIMARY KEY, transcript TEXT, started_at TEXT)")
    conn.execute("CREATE TABLE action_audit (id INTEGER PRIMARY KEY, timestamp TEXT, transcript TEXT, tool_name TEXT, "
                 "tool_input TEXT, result TEXT)")
    now = datetime.now()
    for i in range(4):
        ts = (now - timedelta(days=i)).isoformat(timespec="seconds")
        for phrase, tool, inp in (("how is the weather", "weather", {}), ("start my study setup", "open_app", {"app": "notepad"})):
            conn.execute("INSERT INTO dashboard_sessions (transcript, started_at) VALUES (?, ?)", (phrase, ts))
            conn.execute("INSERT INTO action_audit (timestamp, transcript, tool_name, tool_input, result) VALUES (?,?,?,?,?)",
                         (ts, phrase, tool, json.dumps(inp), "ok"))
    conn.commit()
    conn.close()
    safe = {"weather", "open_app"}
    out = m.suggest(connect, lock, safe, safe, now=now)
    assert [s["phrase"] for s in out] == ["start my study setup"]


def test_the_suggestion_tool_set_holds_action_tools_only(jarvis):
    tools = jarvis._macro_suggest_tools()
    assert "open_app" in tools and not tools & {"web_search", "list_reminders", "recall_facts", "weather", "briefing"}


def _plan(jarvis, status="failed", deps="[]"):
    with jarvis._memory_db_lock:
        conn = jarvis._memory_db_connect()
        try:
            jarvis._ensure_plan_tables(conn) if hasattr(jarvis, "_ensure_plan_tables") else None
            tid = conn.execute("INSERT INTO background_tasks (kind, task, status, started_at) VALUES ('plan', 'p', ?, ?)",
                               (status, "2026-09-30T10:00:00")).lastrowid
            conn.execute("INSERT INTO plan_steps (task_id, step_index, description, depends_on, status, created_at) "
                         "VALUES (?, 0, 'one', ?, 'done', '2026-09-30T10:00:00')", (tid, deps))
            conn.execute("INSERT INTO plan_steps (task_id, step_index, description, depends_on, status, created_at) "
                         "VALUES (?, 1, 'two', ?, 'pending', '2026-09-30T10:00:00')", (tid, deps))
            conn.commit()
        finally:
            conn.close()
    return tid


def test_two_simultaneous_resume_requests_start_the_plan_once(jarvis, monkeypatch):
    jarvis._init_memory_db() if hasattr(jarvis, "_init_memory_db") else None
    started = []
    monkeypatch.setattr(jarvis, "_run_plan", lambda tid: started.append(tid))
    tid = _plan(jarvis)
    replies = []
    ts = [threading.Thread(target=lambda: replies.append(jarvis._resume_plan(tid))) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    time.sleep(0.2)
    assert len(started) == 1 and sum(r.startswith("Resumed plan") for r in replies) == 1
    assert sum("already running" in r for r in replies) == 3


def test_a_plan_with_a_corrupt_dependency_list_or_a_crash_ends_as_failed_not_stuck(jarvis, monkeypatch):
    jarvis._init_memory_db() if hasattr(jarvis, "_init_memory_db") else None
    ran = []
    monkeypatch.setattr(jarvis, "_run_plan_step", lambda d, ctx: ran.append(d) or "did it")
    finished = []
    monkeypatch.setattr(jarvis, "_finish_background_task", lambda tid, st, summ, kind="": finished.append((tid, st, summ)))
    tid = _plan(jarvis, status="running", deps="{not json")
    jarvis._run_plan(tid)
    assert ran == ["two"] and finished[-1][1] == "done"      # the finished step was not run again; the corrupt list didn't stop it
    finished.clear()
    monkeypatch.setattr(jarvis, "_run_plan_impl", lambda t: (_ for _ in ()).throw(RuntimeError("db exploded")))
    jarvis._run_plan(tid)
    assert finished and finished[0][1] == "failed" and "db exploded" in finished[0][2]


# --- J. self-awareness -------------------------------------------------------------------------------------------
def test_dashboard_file_changes_do_not_claim_a_restart_is_needed(tmp_path, monkeypatch):
    import jarvis_selfaware as sa
    root = tmp_path / "code"
    (root / "dashboard_static").mkdir(parents=True)
    (root / "jarvis.py").write_text("a = 1\n")
    (root / "dashboard_static" / "app.js").write_text("//1\n")
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    for name, value in (("_connect", lambda: sqlite3.connect(str(tmp_path / "t.db"))), ("_lock", threading.Lock()),
                        ("_root", root), ("_mtimes", {}), ("_loaded", {}), ("_told_changed", set())):
        monkeypatch.setattr(sa, name, value)
    sa.startup()
    (root / "dashboard_static" / "app.js").write_text("//2 changed\n")
    sa.watch_code()
    assert sa.restart_pending() == []
    assert "no restart needed" in sa.recent(1, "code")[0]["summary"]
    (root / "jarvis.py").write_text("a = 2\n")
    sa.watch_code()
    assert sa.restart_pending() == ["jarvis.py"]


def test_free_text_setting_values_never_reach_the_journal_or_the_prompt(jarvis):
    jarvis._selfaware_setting_hook("JARVIS_OWN_EMAILS", "me@example.com", True)
    jarvis._selfaware_setting_hook("JARVIS_SAFE_MODE", "1", True)
    texts = [r["summary"] for r in jarvis.selfaware.recent(5, "settings")]
    assert "setting JARVIS_OWN_EMAILS changed" in texts and "setting JARVIS_SAFE_MODE set to 1" in texts
    assert "example.com" not in jarvis.selfaware.prompt_line()
