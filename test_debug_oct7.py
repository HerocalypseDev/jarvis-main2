"""Fixes from the owner's debug report of 2026-10-07: false "done" claims and made-up sources, a Word document edited with
invented times and Word force-closed, a time-zone question answered with the clock, a login-file hunt, a fake health
check, a homework error with no reason, and startup checks hitting Gemini's per-minute limit together.
Temp DB only, no network, no real processes."""

import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "d.db"))
    import jarvis as j
    return j


# --- A: claims with nothing behind them ------------------------------------------------------------------------------
@pytest.mark.parametrize("said", [
    "I have gone ahead and cleared it straight out of your deadlines list so your briefing is clean!",
    "That task is completely wiped out and cleared from your schedule, champion!",
    "Coffee CARTesia is completely wiped out, champion! It is gone from your commitments.",
    "I've gone back into your anime document, tracked down the exact premiere times for every show.",
    "I have searched the web and found the real broadcast times.",
])
def test_these_replies_are_unbacked_when_only_lookups_ran(J, said):
    assert J._unbacked_claims(said, ["memory_search", "quick_search", "list_reminders"])


def test_the_same_replies_pass_when_the_right_tool_ran(J):
    assert not J._unbacked_claims("I have cleared it from your deadlines.", ["autonomy"])
    assert not J._unbacked_claims("I searched the web and found the times.", ["web_search"])
    assert not J._unbacked_claims("Coffee is wiped out of your commitments.", ["autonomy"])


def test_where_did_that_come_from_is_looked_up_not_invented(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "a.db"))
    import jarvis_autonomy as au
    from jarvis import _memory_db_connect  # noqa: F401  (imports the schema)
    au.add_commitment({"type": "task", "description": "Coffee CARTesia at 5 PM", "confidence": 0.95,
                       "deadline_iso": datetime.now().replace(hour=17, minute=0, second=0).isoformat(timespec="seconds"),
                       "source_quote": "Coffee with Cartesia: join us on Wednesday at 5"}, "email", "hi@cartesia.example")
    out = au.origin("coffee cartesia")
    assert "email" in out and "Cartesia" in out and "created" in out
    assert "no autonomy record" in au.origin("quantum yoga retreat")
    assert "Say which" in au.origin("where did that come from")


def test_the_autonomy_tool_has_an_origin_action(J):
    out = J._execute_tool("autonomy", {"action": "origin", "query": "something nobody ever made"}, "t")
    assert "no autonomy record" in out


# --- B: documents and programs ---------------------------------------------------------------------------------------
def test_a_script_that_edits_a_document_leaves_a_backup(J, monkeypatch, tmp_path):
    doc = tmp_path / "Notes" / "Anime.docx"
    doc.parent.mkdir()
    doc.write_bytes(b"PK original document bytes")
    code = f"import docx\npath = r'{doc}'\nd = docx.Document(path)\nd.save(path)\n"
    note = J._backup_documents_before_script(code)
    kept = list((doc.parent / ".jarvis-previous").glob("Anime-*.docx"))
    assert len(kept) == 1 and kept[0].read_bytes() == b"PK original document bytes" and "Backed up" in note
    assert J._backup_documents_before_script(f"print(open(r'{doc}','rb').read(4))") == ""  # reading only: no copy


def test_force_closing_a_program_needs_a_yes(J):
    for cmd in ("taskkill /f /im WINWORD.EXE", "Stop-Process -Name chrome -Force", "taskkill /IM notepad.exe /F"):
        assert "force-close" in (J._catastrophic_reason(cmd) or ""), cmd
    assert J._catastrophic_reason("taskkill /im notepad.exe") is None  # a polite close is fine
    assert J._catastrophic_reason("echo hello") is None


def test_run_shell_stages_a_force_kill_instead_of_running_it(J, monkeypatch):
    ran = []
    monkeypatch.setattr(J, "_run_shell_command", lambda c: ran.append(c) or "exit_code=0")
    out = J._execute_tool("run_shell", {"command": "taskkill /f /im WINWORD.EXE"}, "close word")
    assert ran == [] and "staged" in out


# --- C: small fixes --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("said,intent", [
    ("What time is it right now?", "time"), ("what's the time", "time"),
    ("9PM GMT plus eight is what time in my area", "complex"), ("what is the time in Tokyo", "complex"),
    ("what time is the meeting", "complex"), ("what time is it in lagos", "complex"),
])
def test_only_a_plain_clock_question_is_answered_with_the_clock(said, intent):
    import jarvis_latency as l
    assert l.classify_intent(said) == intent


def test_hunting_the_profile_for_login_files_is_refused(J):
    walk = "import os\nprint([os.path.join(d, f) for d, _, fs in os.walk(r'C:\\Users\\x') for f in fs if 'token.pickle' in f])"
    assert "login or credential files" in (J._secret_file_problem(walk) or "")
    assert J._secret_file_problem("Get-ChildItem C:\\Users\\x -Recurse -Filter credentials.json")
    assert J._secret_file_problem("import os\nfor d, _, fs in os.walk('.'):\n    print(len(fs))") is None


@pytest.mark.parametrize("code", ["print('hello')", "python -c \"print('hello')\"",
                                  "print(\"Python tool argument check: all systems operational.\")",
                                  "print('All good, everything is fixed')"])
def test_a_check_that_only_prints_a_message_is_refused(J, code):
    assert "checks nothing" in (J._fake_check_problem(code) or "")


def test_real_code_is_not_called_a_fake_check(J):
    assert J._fake_check_problem("import os\nprint(os.getcwd())") is None
    assert J._fake_check_problem("print(1 + 1)") is None
    assert J._fake_check_problem("x = len('abc')\nprint('ok', x)") is None


def test_the_developer_note_is_not_listed_as_the_owners_problem(J, monkeypatch):
    monkeypatch.setattr(J.doctor, "problems", lambda *a, **k: [
        {"name": "Tool arguments", "detail": "argument repairs: run_python x7", "fix": "sharpen descriptions", "quiet": True},
        {"name": "Gmail sign-in", "detail": "signed in 7 days ago", "fix": "", "status": "warn"}])
    monkeypatch.setattr(J, "_claude_live_problem", lambda: None)
    monkeypatch.setattr(J, "_gemini_live_problem", lambda: None)
    monkeypatch.setattr(J, "_dashboard_get_services_status", lambda: [])
    text = J.self_check_report()
    assert "Gmail sign-in" in text and "Tool arguments" not in text


def test_the_homework_error_says_why_and_that_the_app_is_online(monkeypatch):
    import urllib.error
    import homework_api as h
    monkeypatch.setattr(h, "_token", lambda: "t")
    monkeypatch.setattr(h, "_endpoint", lambda: "https://example.invalid/api/jarvis")

    class Boom:
        def open(self, *a, **k):
            raise urllib.error.URLError(OSError(11001, "getaddrinfo failed"))
    monkeypatch.setattr(h, "_api_opener", Boom())
    with pytest.raises(h.HomeworkApiError) as e:
        h.call("get_overview")
    msg = str(e.value)
    assert "internet" in msg and "hosted online" in msg and "example.invalid" not in msg


# --- D: startup checks one a minute -----------------------------------------------------------------------------------
def test_scheduled_ai_runs_that_are_due_together_start_one_per_gap(J, monkeypatch):
    monkeypatch.setenv("JARVIS_SCHEDULE_STAGGER_S", "45")
    J._sched_stagger["last"] = 0.0
    started = []
    monkeypatch.setattr(J, "_skills_off", lambda: set())
    monkeypatch.setattr(J, "_load_skills", lambda: [{"name": "a"}, {"name": "b"}, {"name": "c"}])
    monkeypatch.setattr(J, "_skill_is_due", lambda s, now: True)
    monkeypatch.setattr(J, "_run_single_flight", lambda name, fn, *a: started.append(name) or True)
    J._start_due_skills(datetime.now())
    assert started == ["skill:a"]                      # the others wait for a later tick
    J._start_due_skills(datetime.now())
    assert started == ["skill:a"]                      # still inside the gap
    J._sched_stagger["last"] = time.monotonic() - 60
    J._start_due_skills(datetime.now())
    assert started == ["skill:a", "skill:a"]           # a minute later the next one starts (a is "due" again here)
    monkeypatch.setenv("JARVIS_SCHEDULE_STAGGER_S", "0")
    started.clear()
    J._start_due_skills(datetime.now())
    assert started == ["skill:a", "skill:b", "skill:c"]


def test_a_watch_and_a_skill_share_the_same_gap(J, monkeypatch):
    monkeypatch.setenv("JARVIS_SCHEDULE_STAGGER_S", "45")
    J._sched_stagger["last"] = time.monotonic()
    started = []
    monkeypatch.setattr(J, "_run_single_flight", lambda name, fn, *a: started.append(name) or True)
    monkeypatch.setattr(J, "_watches", lambda: type("S", (), {"all": lambda self: [{"id": 1}]})())
    monkeypatch.setattr(J.watches_mod, "is_due", lambda w, now: True)
    J._start_due_watches(datetime.now())
    assert started == []
