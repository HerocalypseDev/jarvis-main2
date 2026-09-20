"""Tests for jarvis_autonomy.py, jarvis_dynamic_tools.py, jarvis_memory_consolidation.py and their
dashboard routes. Run: python -m pytest test_autonomy.py -v

Every test uses a throwaway DB (JARVIS_MEMORY_DB_PATH) and fake callbacks; nothing here calls a model,
speaks, or touches the real jarvis_memory.db.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

import pytest


@pytest.fixture()
def A(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.delenv("JARVIS_AUTONOMY_DISABLED", raising=False)
    monkeypatch.delenv("JARVIS_AUTONOMY_ENABLED", raising=False)
    import jarvis_autonomy as a

    a._initialized_paths.clear()
    a._cb.clear()
    a._last_classifier = None
    a._last_context_hash = ""
    a._last_tick_start = None
    a.init_autonomy_tables()
    return a


class Fake:
    """Records callback traffic; `answers` maps a marker in the prompt to the JSON the 'model' returns."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.notified, self.reminders, self.agent_runs, self.tasks, self.audits = [], [], [], [], []
        self.busy = False
        self.quiet = False
        self.bg = 0

    def claude(self, system, user, max_tokens):
        for marker, ans in self.answers.items():
            if marker in user:
                return ans if isinstance(ans, str) else json.dumps(ans)
        return None

    def callbacks(self):
        return {
            "claude": self.claude,
            "notify": lambda text, urgent=False: self.notified.append(text),
            "user_busy": lambda: self.busy,
            "quiet": lambda: self.quiet,
            "audit": lambda *a: self.audits.append(a),
            "create_reminder": lambda text, due: self.reminders.append((text, due)) or f"Reminder set for {due}",
            "run_agent": lambda instr: self.agent_runs.append(instr) or "done",
            "queue_task": lambda d, i, p="normal", dl=None: self.tasks.append(d) or f"Queued task #{len(self.tasks)}: {d!r}",
            "running_background_count": lambda: self.bg,
        }


def _on(a, fake):
    a.configure(fake.callbacks())
    a.set_enabled(True)


def _future(hours):
    return (datetime.now() + timedelta(hours=hours)).isoformat(timespec="seconds")


EXTRACT_MARK = "Conversation turns:"


# ------------------------------------------------------------------------------------------ core
def test_tables_idempotent_and_do_not_collide_with_jarvis_projects_table(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "c.db"))
    conn = sqlite3.connect(tmp_path / "c.db")
    conn.execute("CREATE TABLE projects (name TEXT PRIMARY KEY, status TEXT NOT NULL, next_step TEXT, "
                 "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    conn.commit()
    conn.close()
    import jarvis_autonomy as a

    a._initialized_paths.clear()
    a.init_autonomy_tables()
    a.init_autonomy_tables()
    assert a.get_or_create_project("Thesis") is not None
    # jarvis.py's own table is untouched
    conn = sqlite3.connect(tmp_path / "c.db")
    assert [r[1] for r in conn.execute("PRAGMA table_info(projects)")][:2] == ["name", "status"]


def test_off_by_default_and_hard_kill(A, monkeypatch):
    assert A.enabled() is False
    A.set_enabled(True)
    assert A.enabled() is True
    monkeypatch.setenv("JARVIS_AUTONOMY_DISABLED", "1")
    assert A.enabled() is False
    assert "hard-disabled" in A.set_enabled(True)
    assert A.run_autonomy_tick_once() == {"skipped": "autonomy disabled"}


def test_disabled_extraction_does_nothing(A):
    f = Fake({EXTRACT_MARK: [{"type": "task", "description": "x", "confidence": 0.9}]})
    A.configure(f.callbacks())
    assert A.extract_commitments_and_projects("User: hi") == []


def test_parse_json_variants(A):
    assert A._parse_json('```json\n[{"a": 1}]\n```') == [{"a": 1}]
    assert A._parse_json('Sure! {"b": 2} done') == {"b": 2}
    assert A._parse_json("nope") is None


def test_extraction_creates_commitment_project_and_filters(A):
    f = Fake({EXTRACT_MARK: [
        {"type": "task", "description": "Submit thesis draft", "who_is_responsible": "user",
         "deadline_iso": _future(30), "related_project": "Thesis", "confidence": 0.9, "source_quote": "due friday"},
        {"type": "goal", "description": "Maybe learn piano", "confidence": 0.4},
        {"type": "bogus", "description": "bad type", "confidence": 0.9},
    ]})
    _on(A, f)
    ids = A.extract_commitments_and_projects("User: my thesis draft is due friday")
    assert len(ids) == 1
    c = A._commitment(ids[0])
    assert c["related_project_id"] and c["status"] == "open"
    # same thing again is a duplicate
    assert A.extract_commitments_and_projects("User: my thesis draft is due friday") == []


def test_default_policy_asks_and_creates_pending_suggestion(A):
    f = Fake({EXTRACT_MARK: [{"type": "task", "description": "Call the dentist", "deadline_iso": _future(30),
                              "confidence": 0.95, "source_quote": "call dentist"}]})
    _on(A, f)
    A.extract_commitments_and_projects("User: I need to call the dentist tomorrow")
    pend = A.list_suggestions("pending")
    assert len(pend) == 1 and pend[0]["action_type"] == "reminder"
    assert f.reminders == []  # nothing ran without approval


def test_approve_runs_reminder_and_dismiss_teaches(A):
    f = Fake()
    _on(A, f)
    sid = A.create_suggestion("conversation:reminder", "", "Remind you: x", "ev", "reminder",
                              {"text": "x", "due_iso": _future(2)}, 0.9)
    assert "Approved" in A.approve_suggestion(sid, background=False)
    assert len(f.reminders) == 1
    assert A._rows("SELECT status FROM autonomy_suggestions WHERE id=?", (sid,))[0]["status"] == "executed"
    sid2 = A.create_suggestion("conversation:reminder", "", "Remind you: y", "ev", "reminder", {"text": "y"}, 0.9)
    A.dismiss_suggestion(sid2)
    assert A._rows("SELECT dismissed_streak FROM autonomy_policies WHERE category='conversation:reminder'")[0]["dismissed_streak"] == 1


def test_dry_run_executes_nothing(A):
    f = Fake()
    _on(A, f)
    A.set_dry_run(True)
    sid = A.create_suggestion("c:reminder", "", "t", "e", "reminder", {"text": "x"}, 0.9)
    A.approve_suggestion(sid, background=False)
    assert f.reminders == []
    assert "dry run" in A._rows("SELECT result FROM autonomy_suggestions WHERE id=?", (sid,))[0]["result"]


# ------------------------------------------------------------------------------ policy engine
def test_inbound_content_never_auto_acts_through_category_rule(A):
    A.set_policy("email:reminder", "auto_act", min_confidence=0.5)
    v, why = A.evaluate_policy("email:reminder", "stranger@x.com", "please remind me", 0.99, "reminder", "email")
    assert v == "ask" and "category-wide" in why
    A.set_policy("email:reminder", "auto_act", match_kind="sender", match_value="boss@corp.com", min_confidence=0.5)
    v, _ = A.evaluate_policy("email:reminder", "Boss <boss@corp.com>", "x", 0.99, "reminder", "email")
    assert v == "auto_act"


def test_specificity_sender_beats_category_and_ignore_wins(A):
    A.set_policy("conversation:reminder", "auto_act", min_confidence=0.1)
    A.set_policy("conversation:reminder", "ignore", match_kind="keyword", match_value="spam")
    assert A.evaluate_policy("conversation:reminder", "", "buy spam now", 0.9, "reminder", "conversation")[0] == "ignore"
    assert A.evaluate_policy("conversation:reminder", "", "buy milk", 0.9, "reminder", "conversation")[0] == "auto_act"


def test_low_confidence_downgrades_auto_to_ask(A):
    A.set_policy("conversation:reminder", "auto_act", min_confidence=0.9)
    assert A.evaluate_policy("conversation:reminder", "", "x", 0.7, "reminder", "conversation")[0] == "ask"


def test_learning_promotes_reminders_but_never_email(A):
    for _ in range(3):
        A.record_feedback("conversation:reminder", "", "reminder", True)
        A.record_feedback("conversation:email", "", "email", True)
    assert A.evaluate_policy("conversation:reminder", "", "x", 0.95, "reminder", "conversation")[0] == "auto_act"
    assert A.evaluate_policy("conversation:email", "", "x", 0.95, "email", "conversation")[0] == "ask"


def test_two_dismissals_learn_ignore_and_one_demotes_auto(A):
    A.record_feedback("tick:need:notification", "", "notification", False)
    A.record_feedback("tick:need:notification", "", "notification", False)
    assert A.evaluate_policy("tick:need:notification", "", "x", 0.9, "notification", "tick")[0] == "ignore"
    for _ in range(3):
        A.record_feedback("c:reminder", "", "reminder", True)
    A.record_feedback("c:reminder", "", "reminder", False)
    assert A.evaluate_policy("c:reminder", "", "x", 0.99, "reminder", "conversation")[0] == "ask"


def test_never_creates_user_ignore_rule_and_user_rules_are_not_rewritten(A):
    f = Fake()
    _on(A, f)
    sid = A.create_suggestion("email:calendar", "a@b.c", "t", "e", "calendar", {}, 0.9)
    A.dismiss_suggestion(sid, never=True)
    assert A.evaluate_policy("email:calendar", "", "x", 0.99, "calendar", "email")[0] == "ignore"
    A.record_feedback("email:calendar", "", "calendar", True)
    assert A.evaluate_policy("email:calendar", "", "x", 0.99, "calendar", "email")[0] == "ignore"


def test_recent_dismiss_suppresses_same_category(A):
    A.create_suggestion("c:reminder", "", "one", "e", "reminder", {}, 0.9)
    sid = A.list_suggestions("pending")[0]["id"]
    A.dismiss_suggestion(sid)
    assert A.create_suggestion("c:reminder", "", "two", "e", "reminder", {}, 0.9) is None


def test_suggestion_budget(A, monkeypatch):
    monkeypatch.setenv("JARVIS_AUTONOMY_MAX_SUGGESTIONS_PER_DAY", "2")
    ids = [A.create_suggestion(f"c{i}:reminder", "", f"t{i}", "e", "reminder", {}, 0.9) for i in range(3)]
    assert ids[2] is None


# ------------------------------------------------------------------------------------- the tick
def test_tick_deadline_nudge_fires_once_and_respects_gate(A):
    f = Fake()
    _on(A, f)
    cid = A.add_commitment({"type": "task", "description": "Pay rent", "deadline_iso": _future(1.5), "confidence": 0.9},
                           "conversation")
    f.busy = True
    A.run_autonomy_tick_once()
    assert f.notified == []  # user active: nothing spoken, bucket not consumed
    f.busy = False
    A.run_autonomy_tick_once()
    assert any("Pay rent" in n for n in f.notified)
    n = len(f.notified)
    A.run_autonomy_tick_once()
    assert len(f.notified) == n  # each bucket fires once
    assert "2h" in json.loads(A._commitment(cid)["metadata_json"])["notified"]
    assert A._rows("SELECT COUNT(*) n FROM autonomy_decisions WHERE decision='act'")[0]["n"] >= 1
    assert any(x[0] == "autonomy_decision" for x in f.audits)  # mirrored into action_audit


def test_quiet_mode_blocks_announcements_but_keeps_card(A):
    f = Fake()
    _on(A, f)
    f.quiet = True
    A.create_suggestion("c:reminder", "", "Remind you: q", "e", "reminder", {}, 0.9)
    A.run_autonomy_tick_once()
    assert f.notified == [] and len(A.list_suggestions("pending")) == 1
    f.quiet = False
    A.run_autonomy_tick_once()
    assert any("Suggestion" in n for n in f.notified)


def test_classifier_suggests_and_monitor_stays_silent(A):
    f = Fake({"Current context:": {"has_need": True, "type": "deadline", "description": "Tax form due Friday",
                                   "confidence": 0.9, "suggested_action": "suggest",
                                   "action_payload": {"action_type": "reminder", "details": {"text": "Tax form"}}}})
    _on(A, f)
    A.get_or_create_project("Taxes")
    A.run_autonomy_tick_once(force_classifier=True)
    assert [s["category"] for s in A.list_suggestions("pending")] == ["tick:deadline:reminder"]
    f.answers = {"Current context:": {"has_need": True, "type": "opportunity", "description": "maybe",
                                      "confidence": 0.9, "suggested_action": "monitor", "action_payload": {}}}
    before = len(A.list_suggestions("pending"))
    A.run_autonomy_tick_once(force_classifier=True)
    assert len(A.list_suggestions("pending")) == before


def test_classifier_skipped_when_nothing_to_reason_about(A):
    f = Fake({"Current context:": {"has_need": False}})
    _on(A, f)
    A.run_autonomy_tick_once()
    assert A._rows("SELECT COUNT(*) n FROM autonomy_decisions")[0]["n"] == 0


def test_tick_disabled_is_free(A):
    f = Fake()
    A.configure(f.callbacks())
    assert A.run_autonomy_tick_once()["skipped"] == "autonomy disabled"
    A._started = True
    A.tick()  # must not spawn anything or raise
    assert A._tick_running.is_set() is False


def test_session_summarization_after_idle(A, tmp_path):
    f = Fake({"Conversation turns:": {"summary_text": "Discussed the thesis.", "tags": {"projects": ["Thesis"]}}})
    _on(A, f)
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.execute("CREATE TABLE IF NOT EXISTS memory_turns (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT, timestamp TEXT)")
    old = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
    for i in range(4):
        conn.execute("INSERT INTO memory_turns (role, content, timestamp) VALUES (?, ?, ?)",
                     ("user" if i % 2 == 0 else "assistant", f"turn {i}", old))
    conn.commit()
    conn.close()
    assert A._maybe_summarize(datetime.now()) is True
    assert A._rows("SELECT summary_text FROM conversation_summaries")[0]["summary_text"] == "Discussed the thesis."
    assert A._maybe_summarize(datetime.now()) is False  # already summarised


def test_summarization_waits_while_conversation_is_recent(A, tmp_path):
    f = Fake({"Conversation turns:": {"summary_text": "x"}})
    _on(A, f)
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.execute("CREATE TABLE IF NOT EXISTS memory_turns (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT, timestamp TEXT)")
    for i in range(4):
        conn.execute("INSERT INTO memory_turns (role, content, timestamp) VALUES ('user', ?, ?)",
                     (f"t{i}", datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()
    assert A._maybe_summarize(datetime.now()) is False


# -------------------------------------------------------------------------------- inbound events
def test_inbound_email_makes_pending_calendar_suggestion_never_acts(A):
    f = Fake({"Email subject:": {"meetings": [{"title": "Kickoff", "start_iso": _future(48), "end_iso": None,
                                               "location": "Room 4", "participants": ["a@b.c"], "confidence": 0.9,
                                               "source_quote": "kickoff on Friday"}],
                                 "tasks": [{"description": "Send the deck", "deadline_iso": _future(24),
                                            "confidence": 0.8, "source_quote": "send the deck"}]}})
    _on(A, f)
    A.set_policy("email:calendar", "auto_act", min_confidence=0.1)  # even a category-wide auto rule
    ids = A.process_inbound_message_for_events("Kickoff", "See you Friday", "boss@corp.com", "email")
    assert len(ids) == 2
    assert f.agent_runs == [] and f.reminders == []
    assert {s["action_type"] for s in A.list_suggestions("pending")} == {"calendar", "reminder"}


def test_approving_calendar_suggestion_goes_through_agent_loop(A):
    f = Fake()
    _on(A, f)
    sid = A.create_suggestion("email:calendar", "x@y.z", "Add", "e", "calendar", {"title": "K", "start_iso": _future(5)}, 0.9)
    A.approve_suggestion(sid, background=False)
    assert len(f.agent_runs) == 1 and "Do not send emails" in f.agent_runs[0]


def test_after_turn_only_extracts_on_cues(A, monkeypatch):
    f = Fake()
    _on(A, f)
    calls = []
    monkeypatch.setattr(A, "extract_commitments_and_projects", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(A.threading, "Thread", lambda target, **k: type("T", (), {"start": staticmethod(target)})())
    A.after_turn("what is the capital of France", "Paris", "voice")
    A.after_turn("remind me to call mom tomorrow evening", "ok", "voice")
    A.after_turn("remind me to call mom tomorrow evening", "ok", "autonomy")
    assert len(calls) == 1


# ------------------------------------------------------------------------- campaigns & planner
def test_campaign_requires_approval_then_queues(A):
    f = Fake()
    _on(A, f)
    A.add_project_action("Migration", "Export the old data")
    A._campaign_step(datetime.now(), True)
    assert f.tasks == []
    A.approve_campaign("Migration")
    A._campaign_step(datetime.now(), True)
    assert len(f.tasks) == 1
    assert A._rows("SELECT status FROM autonomy_project_actions")[0]["status"] == "queued"


def test_high_risk_campaign_is_simulated_and_concurrency_respected(A):
    f = Fake()
    _on(A, f)
    A.get_or_create_project("Wipe", risk_level="high")
    A.add_project_action("Wipe", "Delete old backups")
    A.approve_campaign("Wipe")
    A._campaign_step(datetime.now(), True)
    assert f.tasks == []
    assert A._rows("SELECT status FROM autonomy_project_actions")[0]["status"] == "simulated"
    f2 = Fake()
    f2.bg = 5
    A.configure(f2.callbacks())
    A.add_project_action("Migration", "Step two")
    A.approve_campaign("Migration")
    A._campaign_step(datetime.now(), True)
    assert f2.tasks == []


def test_planner_only_queues_accepted_commitments(A):
    f = Fake()
    _on(A, f)
    a = A.add_commitment({"type": "task", "description": "Write report", "deadline_iso": _future(50), "confidence": 0.9}, "conversation")
    A.add_commitment({"type": "task", "description": "Other thing", "deadline_iso": _future(50), "confidence": 0.9}, "conversation")
    A._set_commitment_meta(a, accepted=True)
    A._planner_step(datetime.now(), True)
    assert f.tasks == ["Write report"]


# ------------------------------------------------------------------------- tool + memory reads
def test_handle_tool_refuses_loosening_from_phone_but_allows_disable(A):
    assert "only accepted from the PC" in A.handle_tool({"action": "enable"}, "phone")
    assert A.enabled() is False
    A.handle_tool({"action": "enable"}, "voice")
    assert A.enabled() is True
    A.handle_tool({"action": "disable"}, "phone")
    assert A.enabled() is False
    assert "only accepted" in A.handle_tool({"action": "set_policy", "category": "x", "verdict": "auto_act"}, None)


def test_memory_context_and_agent_line(A):
    f = Fake()
    _on(A, f)
    A.add_commitment({"type": "task", "description": "Buy flowers", "deadline_iso": _future(10),
                      "related_project": "Anniversary", "confidence": 0.9}, "conversation")
    ctx = A.memory_context()
    assert "Buy flowers" in ctx and "Anniversary" in ctx
    assert "Buy flowers" in A.agent_context_line()
    A.set_enabled(False)
    assert A.agent_context_line() == ""


# ------------------------------------------------------------------------------ dynamic tools
@pytest.fixture()
def D(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "d.db"))
    monkeypatch.delenv("JARVIS_DYNAMIC_TOOLS_DISABLED", raising=False)
    monkeypatch.delenv("JARVIS_DYNAMIC_TOOLS_DRY_RUN", raising=False)
    import jarvis_dynamic_tools as d

    d.init_dynamic_tools()
    return d


GOOD = "def add_numbers(a: int, b: int) -> int:\n    return a + b\n"


def test_scanner_blocks_dangerous_code(D):
    bad = {
        "import os\ndef f():\n    return 1\n": "os import",
        "import subprocess\ndef f():\n    return 1\n": "subprocess",
        "import socket\ndef f():\n    return 1\n": "socket",
        "def f(x):\n    return eval(x)\n": "eval",
        "def f(x):\n    exec(x)\n": "exec",
        "def f():\n    return open('a').read()\n": "open",
        "def f():\n    return ().__class__.__bases__\n": "dunder",
        "def f():\n    return getattr(1, 'real')\n": "getattr",
        "def f():\n    return __import__('os')\n": "__import__",
        "def f():\n    return '{0.__class__}'.format(1)\n": "format escape",
        "print('hi')\ndef f():\n    return 1\n": "top-level call",
        "class C:\n    pass\ndef f():\n    return 1\n": "class",
        "def g():\n    return 1\n": "missing entry",
        "def f(:\n": "syntax",
    }
    for code in bad:
        _, reason = D.scan_code(code, "f")
        assert reason, f"should have been rejected: {bad[code]}"
    assert D.scan_code(GOOD, "add_numbers")[1] is None


def test_create_run_persist_reload_and_revoke(D):
    msg = D.create_tool(GOOD, "add_numbers", "Adds two integers", [{"args": {"a": 2, "b": 3}, "expect": 5}])
    assert msg.startswith("Created tool dyn_add_numbers")
    assert D.is_dynamic("dyn_add_numbers")
    schema = D.schemas()[0]
    assert schema["name"] == "dyn_add_numbers"
    assert schema["input_schema"]["properties"]["a"]["type"] == "integer"
    assert schema["input_schema"]["required"] == ["a", "b"]
    assert D.run("dyn_add_numbers", {"a": 4, "b": 5}) == "9"
    D._registry.clear()
    assert D.init_dynamic_tools() == 1  # survives a "restart"
    assert D.revoke("add_numbers").endswith("deleted.") and not D.is_dynamic("dyn_add_numbers")


def test_failing_test_and_dry_run_register_nothing(D):
    assert "Tests failed" in D.create_tool(GOOD, "add_numbers", "d", [{"args": {"a": 1, "b": 1}, "expect": 3}])
    assert "Dry run" in D.create_tool(GOOD, "add_numbers", "d", dry_run=True)
    assert D.list_tools() == []


def test_daily_budget_and_reserved_names(D, monkeypatch):
    monkeypatch.setenv("JARVIS_DYNAMIC_TOOLS_PER_DAY", "1")
    assert D.create_tool(GOOD, "add_numbers", "d").startswith("Created")
    assert "Daily limit" in D.create_tool(GOOD.replace("add_numbers", "add_more"), "add_more", "d")
    D.revoke("add_numbers")  # revoking does not refund the budget
    assert "Daily limit" in D.create_tool(GOOD.replace("add_numbers", "add_more"), "add_more", "d")
    assert "collides" in D.create_tool(GOOD, "add_numbers", "d", reserved_names={"add_numbers"})


def test_tampered_row_is_not_loaded(D):
    D.create_tool(GOOD, "add_numbers", "d")
    conn = sqlite3.connect(D._db_path())
    conn.execute("UPDATE dynamic_tools SET code_text=? WHERE name='add_numbers'",
                 ("import os\ndef add_numbers(a, b):\n    return os.getcwd()\n",))
    conn.commit()
    conn.close()
    assert D.init_dynamic_tools() == 0 and not D.is_dynamic("dyn_add_numbers")


def test_disable_and_kill_switch(D, monkeypatch):
    D.create_tool(GOOD, "add_numbers", "d")
    D.set_enabled("add_numbers", False)
    assert D.schemas() == [] and "not available" in D.run("dyn_add_numbers", {"a": 1, "b": 1})
    D.set_enabled("add_numbers", True)
    monkeypatch.setenv("JARVIS_DYNAMIC_TOOLS_DISABLED", "1")
    assert D.schemas() == [] and "disabled" in D.create_tool(GOOD, "other_tool", "d")


def test_sandbox_timeout_and_runtime_import_block(D, monkeypatch):
    monkeypatch.setattr(D, "RUN_TIMEOUT_S", 2)
    ok, out = D._run_sandboxed("def f():\n    while True:\n        pass\n", "f", {})
    assert not ok and "Timed out" in out
    ok, out = D._run_sandboxed("def f():\n    import math\n    return math.floor(2.5)\n", "f", {})
    assert ok and out == "2"


def test_builtin_self_check(D):
    assert all(D.test_dynamic_tool_creation().values())


# ------------------------------------------------------------------------------- consolidation
def test_consolidation_rules_and_digests(A, tmp_path):
    import jarvis_memory_consolidation as c

    conn = sqlite3.connect(tmp_path / "t.db")
    conn.execute("CREATE TABLE IF NOT EXISTS memory_facts (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, "
                 "key TEXT, content TEXT NOT NULL, created_at TEXT NOT NULL, superseded_at TEXT, superseded_by INTEGER)")
    conn.commit()
    conn.close()
    for _ in range(3):
        A.record_feedback("conversation:reminder", "", "reminder", True)
    old = (datetime.now() - timedelta(days=60)).isoformat(timespec="seconds")
    for i in range(3):
        A._exec("INSERT INTO conversation_summaries (session_id, summary_text, start_time_iso, end_time_iso, tags_json, created_at) "
                "VALUES (?, ?, ?, ?, '{}', ?)", (f"s{i}", f"summary {i}", old, old, old))
    out = c.consolidate(datetime.now(), lambda s, u, m: "Merged digest.", force=True)
    assert out == {"rules": 1, "digests": 1}
    conn = sqlite3.connect(tmp_path / "t.db")
    assert conn.execute("SELECT key FROM memory_facts WHERE superseded_at IS NULL").fetchone()[0] == "rule:autonomy:conversation:reminder"
    assert conn.execute("SELECT COUNT(*) FROM conversation_summaries").fetchone()[0] == 1
    assert c.consolidate(datetime.now(), None) == {"skipped": "ran recently"}
    # a second pass with the same learned rule does not duplicate the fact
    c.consolidate(datetime.now(), None, force=True)
    assert conn.execute("SELECT COUNT(*) FROM memory_facts WHERE key LIKE 'rule:%'").fetchone()[0] == 1


# ------------------------------------------------------------------------------------ dashboard
@pytest.fixture()
def client(A, D, monkeypatch):
    import importlib

    import jarvis_dashboard as dash
    from fastapi.testclient import TestClient

    importlib.reload(dash)
    app = dash._build_app(autonomy=A, dyn_tools=D)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def test_dashboard_status_toggle_and_card_flow(client, A):
    f = Fake()
    A.configure(f.callbacks())
    body = client.get("/api/autonomy").json()
    assert body["available"] and body["enabled"] is False
    assert client.post("/api/autonomy/enabled", json={"enabled": True}).json()["enabled"] is True
    sid = A.create_suggestion("c:reminder", "", "Remind you: z", "ev", "reminder", {"text": "z", "due_iso": _future(3)}, 0.9)
    assert client.get("/api/autonomy").json()["pending_suggestions"][0]["id"] == sid
    assert client.post(f"/api/autonomy/suggestions/{sid}/dismiss").json()["ok"]
    assert client.post(f"/api/autonomy/suggestions/{sid}/bogus").status_code == 400
    r = client.post("/api/autonomy/policies", json={"category": "c:reminder", "verdict": "ignore"}).json()
    assert r["ok"]
    pid = client.get("/api/autonomy").json()["policies"][-1]["id"]
    assert client.delete(f"/api/autonomy/policies/{pid}").json()["ok"]
    assert client.post("/api/autonomy/policies", json={"category": "x", "verdict": "nonsense"}).json()["ok"] is False


def test_dashboard_rejects_foreign_host_and_origin(client):
    assert client.get("/api/autonomy", headers={"host": "evil.example"}).status_code == 403
    r = client.post("/api/autonomy/enabled", json={"enabled": True}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_dashboard_dynamic_tool_management(client, D):
    D.create_tool(GOOD, "add_numbers", "d")
    assert client.get("/api/autonomy").json()["dynamic_tools"][0]["name"] == "add_numbers"
    assert client.post("/api/dynamic_tools/add_numbers/disable").json()["ok"]
    assert D.schemas() == []
    assert client.delete("/api/dynamic_tools/add_numbers").json()["ok"]
    assert client.post("/api/dynamic_tools/x/explode").status_code == 400


def test_autonomy_code_cannot_reach_the_confirmation_gate():
    """Like face: the new modules may never touch the catastrophic gate or import jarvis."""
    import ast
    from pathlib import Path

    banned = {"_pending_action", "_execute_confirmed_action", "skip_confirmation", "_CATASTROPHIC_PATTERNS"}
    for name in ("jarvis_autonomy.py", "jarvis_dynamic_tools.py", "jarvis_memory_consolidation.py"):
        tree = ast.parse(Path(name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in banned, (name, node.id)
            if isinstance(node, ast.Attribute):
                assert node.attr not in banned, (name, node.attr)
            if isinstance(node, ast.Import):
                assert all(a.name != "jarvis" for a in node.names), name
            if isinstance(node, ast.ImportFrom):
                assert node.module != "jarvis", name
