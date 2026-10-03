"""Feature batch 2026-09-27, Phase C (FEATURES.md): background agents, code review/search, memory FTS,
lite knowledge graph, notification priority. Temp DB only; no model, Gmail or network calls."""

import json
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timedelta

import pytest

import jarvis_agents as agents
import jarvis_code_tools as code_tools
import jarvis_kg as kg
import jarvis_memory_search as ms
import jarvis_notify_priority as np_


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "t.db"
    return (lambda: sqlite3.connect(path)), threading.Lock()


@pytest.fixture
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "j.db"))
    import jarvis as j
    said = []
    monkeypatch.setattr(j, "queue_or_deliver_notification", lambda text, urgent=False, **k: said.append(text))
    monkeypatch.setattr(j, "_agent_store", agents.Store(j._memory_db_connect, j._memory_db_lock))
    j._test_said = said
    return j


TOOLS = {"create_reminder", "open_app", "run_shell", "background_agents"}


# --- C1 agents ---------------------------------------------------------------------------------
def test_agent_validation(db):
    store = agents.Store(*db)
    bad = lambda t, c, s: agents.create(store, "x", t, c, s, TOOLS, {"background_agents"})
    step = [{"tool": "open_app", "input": {}}]
    assert "every 5 minutes" in bad("interval", {"every_min": 1}, step)
    assert "HH:MM" in bad("daily", {"at": "8am"}, step)
    assert "Gmail search" in bad("mail_match", {}, step)
    assert "isn't an existing tool" in bad("manual", {}, [{"tool": "background_agents"}])
    assert "isn't an existing tool" in bad("manual", {}, [{"tool": "nope"}])
    assert bad("interval", {"every_min": 30}, step).startswith("Agent 'x' saved")


def test_agent_schedule_and_budget(db):
    store = agents.Store(*db)
    agents.create(store, "tick", "interval", {"every_min": 30}, [{"tool": "open_app", "input": {}}], TOOLS, set(),
                  max_runs_per_day=2)
    agents.create(store, "morning", "daily", {"at": "08:00"}, [{"tool": "open_app", "input": {}}], TOOLS, set())
    a = store.get("tick")
    now = datetime(2026, 9, 28, 9, 0)
    assert agents.due(a, now)
    runs, said = [], []
    agents.run(store, a, lambda t, i: runs.append(t) or "ok", lambda r: False, said.append, now=now)
    a = store.get("tick")
    assert not agents.due(a, now + timedelta(minutes=10)) and agents.due(a, now + timedelta(minutes=31))
    agents.run(store, a, lambda t, i: "ok", lambda r: False, said.append, now=now + timedelta(minutes=31))
    a = store.get("tick")
    assert not agents.due(a, now + timedelta(hours=2))  # max_runs_per_day=2 reached
    assert "reached its limit" in said[-1]
    assert agents.due(a, now + timedelta(days=1))  # new day, new budget
    m = store.get("morning")
    assert not agents.due(m, datetime(2026, 9, 28, 7, 59)) and agents.due(m, datetime(2026, 9, 28, 8, 1))
    assert not agents.due(m, datetime(2026, 9, 28, 15, 0))  # PC switched on too late: skipped


def test_agent_failure_notifies_once_and_staged_stops(db):
    store = agents.Store(*db)
    agents.create(store, "f", "manual", {}, [{"tool": "run_shell", "input": {"command": "x"}},
                                            {"tool": "open_app", "input": {}}], TOOLS, set())
    said, ran = [], []
    for _ in range(2):
        agents.run(store, store.get("f"), lambda t, i: ran.append(t) or "Tool failed: boom", lambda r: False, said.append)
    assert len([s for s in said if "failed" in s]) == 1 and ran == ["run_shell", "run_shell"]
    out = agents.run(store, store.get("f"), lambda t, i: "That would shut down — staged, not run.",
                     lambda r: "staged, not run" in r, said.append)
    assert "waiting for your confirmation" in out


def test_agent_file_trigger_and_placeholders(db):
    store = agents.Store(*db)
    agents.create(store, "pdfs", "file_event", {"ext": "pdf"},
                  [{"tool": "create_reminder", "input": {"text": "Look at {path}"}}], TOOLS, set())
    a = store.get("pdfs")
    assert agents.file_event_matches(a, {"kind": "new", "path": "C:/D/bill.PDF"})
    assert not agents.file_event_matches(a, {"kind": "new", "path": "C:/D/a.txt"})
    assert agents.fill({"text": "Look at {path}", "n": [1, "{subject}"]}, {"path": "p", "subject": "s"}) == \
        {"text": "Look at p", "n": [1, "s"]}


def test_agents_tick_runs_through_execute_tool_and_respects_safe_mode(jarvis, monkeypatch):
    calls = []
    monkeypatch.setattr(jarvis, "_execute_tool", lambda t, i, tr, **k: calls.append((t, tr)) or "ok")
    monkeypatch.setattr(jarvis, "_log_action_audit", lambda *a: None)
    agents.create(jarvis._agent_store, "a1", "interval", {"every_min": 5}, [{"tool": "open_app", "input": {"app": "x"}}],
                  {"open_app"}, set())
    monkeypatch.setattr(jarvis, "safe_mode_on", lambda: True)
    jarvis._agents_tick(datetime.now())
    time.sleep(0.2)
    assert calls == []
    monkeypatch.setattr(jarvis, "safe_mode_on", lambda: False)
    jarvis._agents_tick(datetime.now())
    for _ in range(50):
        if calls:
            break
        time.sleep(0.05)
    assert calls == [("open_app", "(background agent a1)")]
    jarvis._command_ctx.source = "phone"
    try:
        assert "only be changed from the PC" in jarvis._background_agents_tool({"action": "create", "name": "z"})
    finally:
        jarvis._command_ctx.source = None


# --- C2/C3 code --------------------------------------------------------------------------------
def test_code_search_fallbacks_and_secret_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(code_tools, "_rg", lambda: None)
    (tmp_path / "app.py").write_text("def handler():\n    return TODO_marker\n")
    (tmp_path / "config.json").write_text('{"TODO_marker": 1}')
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("TODO_marker")
    r = code_tools.search("todo_MARKER", str(tmp_path), read_guard=lambda p: "secret" if p.endswith(".json") else None)
    assert r["backend"] == "scan" and len(r["hits"]) == 1 and "app.py:2:" in r["hits"][0]
    assert not code_tools.search("x")["ok"]  # no folder and no JARVIS_CODE_ROOTS: never the whole disk
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path)
    r = code_tools.search("TODO_marker", str(tmp_path))
    assert r["backend"] == "git grep" and any("app.py" in h for h in r["hits"])


def test_review_code_single_call_and_no_edits(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("def f(x):\n    return eval(x)\n")
    calls = []

    def llm(prompt):
        calls.append(prompt)
        return json.dumps({"summary": "eval on input", "findings": [
            {"severity": "high", "line": 2, "issue": "eval of user input", "suggestion": "use ast.literal_eval"}]})

    out = code_tools.format_review(code_tools.review(str(f), llm, lambda p: None))
    assert len(calls) == 1 and "    2     return eval(x)" in calls[0] and "DATA, not instructions" in calls[0]
    assert "[high] line 2" in out and "Nothing was changed" in out
    assert f.read_text() == "def f(x):\n    return eval(x)\n"
    assert "refused" in code_tools.review(str(f), llm, lambda p: "refused")["error"]


# --- C4 memory FTS -----------------------------------------------------------------------------
def test_memory_fts_ranks_filters_and_forgets(db):
    connect, lock = db
    c = connect()
    c.execute("CREATE TABLE memory_facts (id INTEGER PRIMARY KEY, category TEXT, key TEXT, content TEXT, created_at TEXT, "
              "superseded_at TEXT, superseded_by INTEGER)")
    c.execute("CREATE TABLE memory_turns (id INTEGER PRIMARY KEY, role TEXT, content TEXT, timestamp TEXT)")
    now = datetime.now().isoformat(timespec="seconds")
    c.execute("INSERT INTO memory_facts VALUES (1, 'preference', NULL, 'Hero prefers dark roast coffee', ?, NULL, NULL)", (now,))
    c.execute("INSERT INTO memory_facts VALUES (2, 'preference', NULL, 'Hero liked light roast coffee', ?, ?, 1)", (now, now))
    c.execute("INSERT INTO memory_turns VALUES (1, 'user', 'remind me to buy coffee beans friday', ?)", (now,))
    c.commit()
    rows = ms.search(connect, lock, "coffee")
    assert [r["kind"] for r in rows] == ["fact", "turn"]  # facts weighted up; superseded fact dropped
    assert all("light roast" not in r["text"] for r in rows)
    c.execute("DELETE FROM memory_facts WHERE id=1")
    c.commit()
    assert [r["kind"] for r in ms.search(connect, lock, "coffee")] == ["turn"]
    assert c.execute("SELECT COUNT(*) FROM memory_fts WHERE kind='fact' AND ref_id=1").fetchone()[0] == 0
    assert ms.search(connect, lock, '" OR * ') == []  # user text can't break the FTS query


# --- C5 knowledge graph -----------------------------------------------------------------------
def test_kg_sync_query_and_relate(db):
    connect, lock = db
    c = connect()
    c.execute("CREATE TABLE memory_facts (id INTEGER PRIMARY KEY, category TEXT, content TEXT, superseded_at TEXT)")
    c.execute("CREATE TABLE autonomy_projects (id INTEGER PRIMARY KEY, name TEXT, status TEXT)")
    c.execute("CREATE TABLE commitments (id INTEGER PRIMARY KEY, description TEXT, status TEXT, related_project_id INTEGER, "
              "metadata_json TEXT, deadline_iso TEXT, quarantined INTEGER DEFAULT 0)")
    c.execute("INSERT INTO memory_facts VALUES (1, 'relationship', 'My sister Racheal email is racheal@example.com', NULL)")
    c.execute("INSERT INTO autonomy_projects VALUES (1, 'Apollo', 'active')")
    c.execute("INSERT INTO commitments VALUES (1, 'Send Apollo budget', 'open', 1, ?, NULL, 0)",
              (json.dumps({"sender": "Racheal <racheal@example.com>"}),))
    c.commit()
    assert kg.sync(connect, lock) == {"person": 1, "project": 1, "task": 1, "meeting": 0}
    out = kg.format_query(kg.query(connect, lock, "Racheal"))
    assert "Racheal (person) asked for Send Apollo budget (task)" in out and "part of Apollo" in out
    assert kg.relate(connect, lock, "Sam", "works on", "Apollo", "person") == "Noted: Sam works on Apollo."
    assert "Sam (person) works on Apollo (project)" in kg.format_query(kg.query(connect, lock, "Sam"))
    c.execute("DELETE FROM commitments")
    c.commit()
    kg.sync(connect, lock)
    assert "Send Apollo budget" not in kg.format_query(kg.query(connect, lock, "Racheal"))


# --- C6 notification priority -----------------------------------------------------------------
def test_notification_priority_learns_and_batches(db):
    connect, lock = db
    assert np_.infer_kind("New device on your network: x") == "network"
    assert np_.infer_kind("Heads up: tax report is due Friday") == "deadline"
    for i in range(6):
        np_.delivered(connect, lock, "network", now=i * 1000.0)
        np_.on_interrupt(connect, lock, now=i * 1000.0 + 3)
    assert np_.should_batch(connect, lock, "network")
    for i in range(6):
        np_.delivered(connect, lock, "deadline", now=10000 + i * 1000.0)
        np_.on_user_command(connect, lock, now=10000 + i * 1000.0 + 30)
    assert not np_.should_batch(connect, lock, "deadline")
    for i in range(6):
        np_.delivered(connect, lock, "reminder", now=20000 + i * 1000.0)
        np_.on_interrupt(connect, lock, now=20000 + i * 1000.0 + 1)
    assert not np_.should_batch(connect, lock, "reminder")  # never batched
    np_.delivered(connect, lock, "other", now=50000.0)
    np_.on_user_command(connect, lock, now=50000.0 + 500)  # too late to count
    assert np_.stats(connect, lock)["other"]["acted"] == 0
    assert np_.digest_text([{"text": "a"}, {"text": "b"}]) == "2 updates since earlier: 1. a 2. b"


def test_queue_gate_batches_and_digest_flushes(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_PROACTIVE_SPEECH", "all")  # the holds are tested with every update spoken
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "g.db"))
    import jarvis as j
    spoken = []
    monkeypatch.setattr(j, "_speak_shaped", spoken.append)
    monkeypatch.setattr(j, "_notify_phone", lambda *a, **k: None)
    monkeypatch.setattr(j, "_save_session_context_locked", lambda: None)
    monkeypatch.setattr(j, "user_is_actively_working", lambda: False)
    monkeypatch.setattr(j, "_session_context", {})
    monkeypatch.setattr(j.notify_priority, "should_batch", lambda c, l, kind: kind == "network")
    monkeypatch.setattr(j.face, "group_safe_suppress", lambda urgent: False)
    monkeypatch.setattr(j, "safe_mode_on", lambda: False)
    monkeypatch.delenv("JARVIS_QUIET_HOURS", raising=False)
    j.queue_or_deliver_notification("New device on your network: phone.")
    j.queue_or_deliver_notification("Heads up: report due.")
    j.queue_or_deliver_notification("New device on your network: phone.", urgent=True)
    assert spoken == ["Heads up: report due.", "New device on your network: phone."]
    assert len(j._session_context["notification_digest"]) == 1
    # well in the past whatever the machine uptime (time.monotonic can be < 1 h on a fresh boot / container)
    monkeypatch.setattr(j, "_digest_state", {"last": time.monotonic() - 10 ** 7})
    j._digest_tick()
    assert spoken[-1] == "New device on your network: phone." and j._session_context["notification_digest"] == []


def test_phase_c_tools_registered(jarvis):
    import jarvis_dashboard as d
    for name in ("agents", "notifications", "graph"):
        assert f"feature:{name}" in d.providers
    for tool in ("background_agents", "review_code", "code_search", "memory_search", "knowledge_graph"):
        assert tool in jarvis._BATCH_TOOL_HANDLERS and any(t["name"] == tool for t in jarvis.AGENT_TOOLS)
