"""Start lines (2026-10-05): every skill / scheduled job / routine / one-off command says one sentence about ITS task
when it starts. Temp DB only, no network, no audio."""

import json
import sqlite3
import threading

import pytest

import jarvis_startline as sl


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "s.db"))
    monkeypatch.setenv("JARVIS_ACK_PHRASES", "1")
    import jarvis as j
    return j


@pytest.mark.parametrize("said,line", [
    ("can you check the git status of my project", "Sure, I'll check the git status of your project."),
    ("Hey Jarvis, search the web for the latest Arsenal score please.",
     "Sure, I'll search the web for the latest Arsenal score."),
    ("I need you to summarize my last three emails from Sam", "Sure, I'll summarize your last three emails from Sam."),
    ("remind me to call mum at 5", "Sure, I'll remind you to call mum at 5."),
    ("restart yourself", "Sure, I'll restart myself."),
])
def test_a_request_becomes_a_line_about_that_task(said, line):
    assert sl.from_request(said) == line


@pytest.mark.parametrize("said", [
    "what's the weather", "shut down my computer", "delete my downloads folder", "format the D drive",
    "restart my computer", "could you tell me what you think", "how are you", "", "open notepad\n[selected text]",
])
def test_questions_chat_and_dangerous_requests_keep_the_generic_lead_in(said):
    """Nothing is promised before the confirmation gate decides, and a question isn't echoed as a task."""
    assert sl.from_request(said) is None


def test_a_line_is_built_from_a_description_when_none_was_stored():
    assert sl.from_text("Runs automatically every hour to check the price of bitcoin, and tell me if it moved",
                        "btc_watch").startswith("Sure, I'll check the price of bitcoin")
    assert sl.from_text("Anything the user asks about recipes", "cooking_helper") == "Starting cooking helper."
    assert sl.clean("  Checking\nyour mail ") == "Checking your mail."
    assert len(sl.clean("word " * 80)) <= sl.MAX_CHARS + 1


def test_a_new_skill_stores_its_line_and_an_update_keeps_it(J, monkeypatch, tmp_path):
    monkeypatch.setattr(J, "_skills_dir", lambda: tmp_path)
    J.save_skill("btc_watch", "Check bitcoin", "1. web_search bitcoin price", {"every_minutes": 60},
                 "Checking the bitcoin price for you.")
    saved = json.loads((tmp_path / "btc_watch.json").read_text(encoding="utf-8"))
    assert saved["start_line"] == "Checking the bitcoin price for you."
    J.save_skill("btc_watch", "", "1. web_search bitcoin price in naira")           # an update with no line
    saved = json.loads((tmp_path / "btc_watch.json").read_text(encoding="utf-8"))
    assert saved["start_line"] == "Checking the bitcoin price for you." and saved["schedule"] == {"every_minutes": 60}
    J.save_skill("tidy", "Clean up my downloads folder", "1. ...")               # the model forgot the line
    assert json.loads((tmp_path / "tidy.json").read_text(encoding="utf-8"))["start_line"] == \
        "Sure, I'll clean up your downloads folder."


def test_a_command_gets_its_routine_or_named_skill_line_else_its_own_words(J, monkeypatch):
    skills = [{"name": "morning_briefing", "description": "d", "instructions": "i",
               "start_line": "Getting your morning briefing ready."},
              {"name": "gmail_watch", "description": "d", "instructions": "i"}]
    monkeypatch.setattr(J, "_active_skills", lambda: skills)
    assert J._command_start_line("run my morning briefing") == "Getting your morning briefing ready."
    assert J._command_start_line("x", {"name": "focus", "instructions": "i", "start_line": "Setting up focus time."}) \
        == "Setting up focus time."
    assert J._command_start_line("can you check the git status of my project") == \
        "Sure, I'll check the git status of your project."
    assert J._command_start_line("run shutdown /s /t 0") is None  # the gate stages it: no promise


def test_the_task_line_replaces_the_generic_lead_in(J, monkeypatch):
    said = []
    monkeypatch.setattr(J, "_start_announcement", lambda line: said.append(("line", line)) or True)
    monkeypatch.setattr(J, "_start_ack", lambda kind: said.append(("generic", kind)) or True)
    monkeypatch.setattr(J, "_active_skills", lambda: [])
    J._maybe_ack_before_task("can you search the web for flights to Abuja")
    assert said == [("line", "Sure, I'll search the web for flights to Abuja.")]
    said.clear()
    J._maybe_ack_before_task("delete everything in my downloads")
    assert said == [("generic", "action")]


def _run_skill(J, monkeypatch, skill):
    spoken, sessions = [], []
    monkeypatch.setattr(J, "run_agent_loop", lambda *a, **k: "Nothing new.")
    monkeypatch.setattr(J, "speak_text", lambda text, **k: spoken.append(text))
    monkeypatch.setattr(J, "_start_line_held", lambda: False)
    monkeypatch.setattr(J, "queue_or_deliver_notification", lambda *a, **k: None)
    monkeypatch.setattr(J.dashboard, "start_session", lambda src, t: sessions.append((src, t)) or 1)
    monkeypatch.setattr(J.dashboard, "end_session", lambda *a, **k: sessions.append(("end", a[1])))
    monkeypatch.setattr(J.dashboard, "notify", lambda *a, **k: None)
    J._run_scheduled_skill(skill)
    return spoken, sessions


def test_a_scheduled_skill_says_its_line_only_when_it_speaks_anyway(J, monkeypatch):
    loud = {"name": "morning_briefing", "description": "d", "instructions": "i", "announce": True,
            "start_line": "Getting your morning briefing ready."}
    spoken, sessions = _run_skill(J, monkeypatch, loud)
    assert spoken == ["Getting your morning briefing ready."]
    quiet = {"name": "gmail_watch", "description": "d", "instructions": "i",
             "start_line": "Checking your Gmail for anything new."}
    spoken, sessions = _run_skill(J, monkeypatch, quiet)
    assert spoken == []  # the quiet rule holds; the line is on the dashboard instead
    assert sessions[0] == ("scheduled", "gmail_watch: Checking your Gmail for anything new.")
    assert sessions[-1] == ("end", "done")


def test_a_held_moment_drops_the_line(J, monkeypatch):
    spoken = []
    monkeypatch.setattr(J, "speak_text", lambda text, **k: spoken.append(text))
    monkeypatch.setattr(J.sleep_mode, "is_active", lambda: True)
    assert J._say_start_line("Getting your morning briefing ready.") is False and spoken == []


def test_a_job_keeps_the_line_it_was_scheduled_with(J, monkeypatch, tmp_path):
    import jarvis_deferred as deferred
    from datetime import datetime, timedelta
    store = deferred.Store(lambda: sqlite3.connect(tmp_path / "jobs.db"), threading.Lock())
    jid, _ = deferred.schedule(store, "run the internet speed test", datetime.now() + timedelta(minutes=10),
                               start_line="Running your speed test now, like you asked.")
    job = store.q("SELECT * FROM autonomy_deferred_jobs WHERE id=?", (jid,))[0]
    assert job["start_line"] == "Running your speed test now, like you asked."
    spoken = []
    monkeypatch.setattr(J, "_say_start_line", lambda line: spoken.append(line) or True)
    monkeypatch.setattr(J, "run_agent_loop", lambda *a, **k: "Download 20 Mbps.")
    monkeypatch.setattr(J, "_finish_deferred_job", lambda *a, **k: None)
    monkeypatch.setattr(J.dashboard, "start_session", lambda *a: 1)
    monkeypatch.setattr(J.dashboard, "notify", lambda *a, **k: None)
    J._run_deferred_job(dict(job, attempts=1, origin="user"))
    assert spoken == ["Running your speed test now, like you asked."]
    spoken.clear()
    J._run_deferred_job(dict(job, attempts=1, origin="autonomy", start_line=None))
    assert spoken == []  # a job autonomy made on its own stays quiet


def test_a_routine_keeps_its_line_when_re_saved_without_one(tmp_path):
    import jarvis_macros as m
    connect, lock = (lambda: sqlite3.connect(tmp_path / "m.db")), threading.Lock()
    m.save(connect, lock, "study", ["study time now"], [], set(), instructions="summarise my notes and quiz me",
           start_line="Getting your study session ready.")
    m.save(connect, lock, "study", ["study time now"], [], set(), instructions="summarise my notes and quiz me hard")
    assert m.list_macros(connect, lock)[0]["start_line"] == "Getting your study session ready."


def test_scheduled_runs_stay_out_of_the_palettes_recent_commands(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "d.db"))
    import importlib
    import jarvis_dashboard as d
    d = importlib.reload(d)
    d.start_session("voice", "open notepad")
    d.start_session("scheduled", "gmail_watch: Checking your Gmail.")
    d.start_session("autonomy", "(autonomy deferred) run the tests")
    assert [r["text"] for r in d.recent_commands(10)] == ["open notepad"]


def test_every_own_skill_has_a_start_line():
    from pathlib import Path
    files = sorted((Path(__file__).parent / "skills").glob("*.json"))
    if not files:
        pytest.skip("no own skills in this copy")
    for f in files:
        assert sl.clean(json.loads(f.read_text(encoding="utf-8")).get("start_line")), f.name
