"""Phrase routines and "update time" (2026-10-03 debug report): a self-made "update time" macro called autonomy_skill
without its required action, did nothing, and said "Done". Owner's rules: every routine they make runs instantly with no
AI call when its steps are fixed actions, and uses the AI by itself when it needs thinking (no questions); "update time"
pulls, restarts Jarvis only if the pull worked, and says what changed after. Temp DB only; git and restart are faked."""

import json
import subprocess
import time

import pytest

import jarvis_latency as latency
import jarvis_macros as macros


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "r.db"))
    import jarvis as j
    monkeypatch.setattr(j, "UPDATE_NOTE_FILE", tmp_path / "update_note.json")
    said = []
    monkeypatch.setattr(j, "queue_or_deliver_notification", lambda text, urgent=False, **k: said.append(text))
    monkeypatch.setattr(j, "_start_announcement", lambda line: None)
    j._test_said = said
    j._command_ctx.source = "voice"
    yield j
    j._command_ctx.source = None


def _create(J, **inp):
    return J._macros_tool(dict(inp, action="create"))


# ---------------------------------------------------------------------------------------------- the report
def test_the_broken_update_macro_is_refused_or_made_to_work(J):
    bad_step = [{"tool": "autonomy_skill", "input": {"name": "update_and_restart"}}]
    out = _create(J, name="update_and_restart_macro", phrases=["start my updates"], steps=bad_step)
    assert out.startswith("Step 1 (autonomy_skill) wouldn't work") and "action" in out  # no instructions: refused
    out = _create(J, name="updates", phrases=["start my updates"], steps=bad_step,
                  instructions="run git pull, then restart Jarvis")
    assert "with the AI each time" in out and "can't run as written" in out  # it still works, through the AI


def test_a_failing_step_is_never_reported_as_done(J, monkeypatch):
    macros.save(J._memory_db_connect, J._memory_db_lock, "pull", ["pull my code"],
                [{"tool": "run_shell", "input": {"command": "git pull"}}, {"tool": "restart_jarvis", "input": {}}],
                {"run_shell", "restart_jarvis"})
    ran = []
    monkeypatch.setattr(J, "_execute_tool", lambda tool, inp, transcript, **k: ran.append(tool) or (
        "exit_code=1\nstderr: fatal: unable to access github"))
    out = J._macro_reply("pull my code")
    assert out.startswith("pull stopped at step 1 (run_shell) failed") and ran == ["run_shell"]  # no restart after it
    monkeypatch.setattr(J, "_execute_tool", lambda tool, inp, transcript, **k: "Tool failed: autonomy_skill needs 'action'")
    assert "failed" in J._macro_reply("pull my code")


def test_missing_parameters_are_failures_everywhere(J):
    out = J._execute_tool("autonomy_skill", {"name": "update_and_restart"}, "update time")
    assert out.startswith("Tool failed: autonomy_skill needs 'action'") and J._looks_failed(out)


# ---------------------------------------------------------------------------------------------- instant or AI
@pytest.mark.parametrize("instructions, steps, mode", [
    ("check the weather", [{"tool": "weather", "input": {}}], "instant"),
    ("open my browser and set the volume to 40", [{"tool": "open_app", "input": {"app": "browser"}},
                                                  {"tool": "system_action", "input": {"system_action": "volume_up"}}], "instant"),
    ("tell me if I need an umbrella today", [{"tool": "weather", "input": {}}], "ai"),
    ("summarise my unread emails", [{"tool": "mcp_gmail_search_emails", "input": {"query": "is:unread"}}], "ai"),
    ("reply to my last email", [], "ai"),
    ("remind me about {subject}", [{"tool": "create_reminder", "input": {"text": "{subject}"}}], "ai"),
])
def test_jarvis_decides_instant_or_ai_by_itself(instructions, steps, mode):
    known = {"weather", "open_app", "system_action", "mcp_gmail_search_emails", "create_reminder"}
    assert macros.classify("", instructions, steps, None, known)[0] == mode


def test_weather_time_runs_instantly_and_says_the_result(J, monkeypatch):
    out = _create(J, name="weather time", phrases=["weather time"], instructions="check the weather",
                  steps=[{"tool": "weather", "input": {}}])
    assert "instantly, no AI call" in out
    monkeypatch.setattr(J, "run_agent_loop", lambda *a, **k: pytest.fail("an instant routine makes no AI call"))
    monkeypatch.setattr(J, "_execute_tool", lambda tool, inp, transcript, **k:
                        "Lagos: 29 degrees and cloudy, 40 percent chance of rain later.")
    assert J._macro_reply("weather time") == "Lagos: 29 degrees and cloudy, 40 percent chance of rain later."


def test_an_ai_routine_sends_its_instructions_to_the_ai(J):
    out = _create(J, name="inbox time", phrases=["inbox time"], instructions="summarise my unread emails",
                  steps=[{"tool": "mcp_gmail_search_emails", "input": {"query": "is:unread"}}])
    assert "with the AI each time" in out
    reply, routine = J._macro_route("Inbox time.")
    assert reply is None and routine["name"] == "inbox time"
    assert "summarise my unread emails" in J._routine_instruction(routine, "Inbox time.")


def test_an_ai_routine_runs_through_the_agent_loop(J, monkeypatch):
    _create(J, name="inbox time", phrases=["inbox time"], instructions="summarise my unread emails")
    for name, fake in (("_log_action_audit", lambda *a, **k: None), ("_append_history", lambda *a, **k: None),
                       ("flush_pending_notifications", lambda: None), ("speak_text", lambda t: None)):
        monkeypatch.setattr(J, name, fake)
    monkeypatch.setattr(J.autonomy, "after_turn", lambda *a, **k: None)
    seen = []
    monkeypatch.setattr(J, "run_agent_loop", lambda transcript, *a, **k: seen.append(transcript) or "You have 2 new emails.")
    J.handle_text_command("inbox time", source="text")
    assert seen and "routine 'inbox time'" in seen[0] and "summarise my unread emails" in seen[0]


# ---------------------------------------------------------------------------------------------- update time
@pytest.mark.parametrize("said", ["Update time", "update time.", "Hey Jarvis, update time", "it's update time",
                                  "update yourself", "git pull and restart", "update time now please"])
def test_update_time_is_a_built_in_command(said):
    assert latency.classify_intent(said) == "update"


@pytest.mark.parametrize("said", ["what time is the update", "update my calendar", "when is update time for windows"])
def test_other_update_sentences_are_not(said):
    assert latency.classify_intent(said) != "update"


def test_the_old_update_time_macro_no_longer_wins(J):
    J._memory_db_connect().close()
    macros._q(J._memory_db_connect, J._memory_db_lock,
              "INSERT INTO macros (name, phrases, steps, enabled, created_at) VALUES (?, ?, ?, 1, ?)",
              ("update_and_restart_macro", json.dumps(["update time"]),
               json.dumps([{"tool": "autonomy_skill", "input": {"name": "update_and_restart"}}]), "2026-10-03"), write=True)
    assert J._macro_route("Update time") == (None, None)  # the built-in command answers instead
    assert "own commands" in _create(J, name="x", phrases=["update time"], steps=[{"tool": "weather", "input": {}}])


def _fake_git(monkeypatch, J, pull_rc=0, pull_err="", subjects=("Add tab reading", "Fix macros")):
    heads = iter(["aaa", "bbb"])

    def git(*args, timeout=30):
        if args[0] == "rev-parse":
            return subprocess.CompletedProcess(args, 0, next(heads, "bbb") + "\n", "")
        if args[0] == "pull":
            return subprocess.CompletedProcess(args, pull_rc, "", pull_err)
        if args[0] == "log":
            return subprocess.CompletedProcess(args, 0, "\n".join(subjects) + "\n", "")
        raise AssertionError(args)

    monkeypatch.setattr(J, "_git", git)


def test_update_pulls_restarts_and_says_what_changed(J, monkeypatch):
    _fake_git(monkeypatch, J, subjects=("Add tab reading", "Fix macros", "Opera GX setting", "Ask first rule"))
    calls = []
    monkeypatch.setattr(J, "_execute_tool", lambda tool, inp, transcript, **k: calls.append(tool) or
                        "Restart scheduled: Jarvis will close in a few seconds and reopen with the latest code.")
    monkeypatch.setattr(J, "run_agent_loop", lambda *a, **k: pytest.fail("update time needs no model call"))
    assert J._deterministic_intent_reply("update", "update time") == \
        "Pulled 4 new changes. Restarting now, back in about half a minute."
    assert calls == ["restart_jarvis"]
    # ...and after the restart, once:
    assert J._update_note_line() == ("Updated and restarted. New: Add tab reading; Fix macros; Opera GX setting; "
                                     "and 1 more change.")
    assert J._update_note_line() is None and not J.UPDATE_NOTE_FILE.exists()


def test_a_failed_pull_never_restarts(J, monkeypatch):
    _fake_git(monkeypatch, J, pull_rc=1, pull_err="fatal: unable to access 'https://github.com/x/y.git/': "
                                                   "Could not resolve host: github.com")
    monkeypatch.setattr(J, "_execute_tool", lambda *a, **k: pytest.fail("no restart after a failed pull"))
    out = J._update_and_restart_reply("update time")
    assert out == ("Update failed: I couldn't reach GitHub (is the internet on?). I didn't restart, so I'm still "
                   "running as before.")
    _fake_git(monkeypatch, J, pull_rc=1, pull_err="error: Your local changes to the following files would be "
                                                   "overwritten by merge:\n\tjarvis.py\nPlease commit your changes")
    assert "changed and the update would overwrite them (jarvis.py)" in J._update_and_restart_reply("update time")


def test_a_refused_restart_says_so_and_leaves_no_note(J, monkeypatch):
    _fake_git(monkeypatch, J, subjects=())
    monkeypatch.setattr(J, "_execute_tool", lambda *a, **k: "Not restarting: a background task is still running.")
    out = J._update_and_restart_reply("update time")
    assert out == "Already up to date, but I didn't restart: Not restarting: a background task is still running."
    assert not J.UPDATE_NOTE_FILE.exists()


def test_an_old_update_note_is_not_announced(J):
    J.UPDATE_NOTE_FILE.write_text(json.dumps({"at": time.time() - 3600, "subjects": ["x"], "count": 1}))
    assert J._update_note_line() is None and not J.UPDATE_NOTE_FILE.exists()
