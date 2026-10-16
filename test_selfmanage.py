"""Jarvis managing what the owner can manage (2026-10-16): the `settings` and `stop_background_task` tools, and the
`pending` / `logs` pages of dashboard_data. Temp DB and temp .env only."""

import pytest

import jarvis_selfmanage as sm

LISTING = {
    "known": [
        {"key": "JARVIS_WAKE_WORD", "label": "Say 'Hey Jarvis' to wake me", "kind": "bool", "value": "0",
         "applies": "now", "help": "Opt-in wake word."},
        {"key": "JARVIS_FOLLOWUP_S", "label": "Follow-up window (seconds)", "kind": "number", "value": "5",
         "applies": "now", "help": "Mic stays open after a reply."},
        {"key": "JARVIS_MAIL_AUTOREPLY", "label": "Mail auto-reply", "kind": "bool", "value": "1", "applies": "now",
         "help": "Answers incoming mail."},
        {"key": "JARVIS_FACE_ENABLED", "label": "Face recognition", "kind": "bool", "value": "0", "applies": "restart"},
        {"key": "JARVIS_AUTONOMY_EMAIL_MAX_PER_DAY", "label": "Mail limit per day", "kind": "number", "value": "20",
         "applies": "now", "help": "Mail cap."},
        {"key": "JARVIS_SAFE_MODE", "label": "Safe mode", "kind": "bool", "value": "0", "applies": "now"},
    ],
    "other": [{"key": "ANTHROPIC_API_KEY", "secret": True, "set": True, "value": None},
              {"key": "MY_PLAIN_THING", "secret": False, "set": True, "value": "x"}],
}


def test_find_matches_words_and_exact_keys():
    assert [r["key"] for r in sm.find(LISTING, "wake word")] == ["JARVIS_WAKE_WORD"]
    assert [r["key"] for r in sm.find(LISTING, "JARVIS_FOLLOWUP_S")] == ["JARVIS_FOLLOWUP_S"]
    assert [r["key"] for r in sm.find(LISTING, "mail auto reply")] == ["JARVIS_MAIL_AUTOREPLY"]
    assert sm.find(LISTING, "banana") == []


def test_secret_values_never_shown():
    row = sm.find(LISTING, "ANTHROPIC_API_KEY")[0]
    text = sm.show(row)
    assert "(set)" in text and "sk-" not in text


def test_what_the_model_may_set():
    ok = sm.find(LISTING, "wake word")[0]
    assert sm.set_problem(ok) is None
    assert "secret" in sm.set_problem(sm.find(LISTING, "ANTHROPIC_API_KEY")[0])
    assert "Settings page" in sm.set_problem(sm.find(LISTING, "MY_PLAIN_THING")[0])  # not on the curated list
    assert "camera" in sm.set_problem(sm.find(LISTING, "JARVIS_FACE_ENABLED")[0])
    assert sm.set_problem(None)


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "s.db"))
    import jarvis as j
    j._command_ctx.source = "voice"
    for a in ("untrusted_origin", "outside_text_seen", "hands_free", "wake", "autonomous"):
        setattr(j._command_ctx, a, False)
    saved = {}
    monkeypatch.setattr(j.settings, "list_settings", lambda: LISTING)
    monkeypatch.setattr(j.settings, "set_setting",
                        lambda k, v: saved.update({k: v}) or {"ok": True, "key": k, "applies": "now"})
    j._saved = saved
    yield j
    j._command_ctx.source = None


def test_settings_get_and_set_by_name(J):
    assert "JARVIS_WAKE_WORD" in J._execute_tool("settings", {"action": "get", "query": "wake word"}, "wake word?")
    out = J._execute_tool("settings", {"action": "set", "name": "wake word", "value": "1"}, "turn on the wake word")
    assert "changed" in out and "applies now" in out
    assert J._saved == {"JARVIS_WAKE_WORD": "1"}


def test_settings_set_refuses_secrets_paths_and_ambiguity(J):
    out = J._execute_tool("settings", {"action": "set", "name": "ANTHROPIC_API_KEY", "value": "x"}, "set my key")
    assert out.startswith("Refused") and J._saved == {}
    out = J._execute_tool("settings", {"action": "set", "name": "face recognition", "value": "1"}, "turn on face")
    assert out.startswith("Refused") and J._saved == {}
    out = J._execute_tool("settings", {"action": "set", "name": "mail", "value": "1"}, "mail")
    assert "ask the user which one" in out and J._saved == {}
    out = J._execute_tool("settings", {"action": "set", "name": "wake word"}, "wake word")
    assert out.startswith("Tool failed") and J._saved == {}


def test_settings_set_only_for_the_owner(J):
    for attr, src in (("untrusted_origin", "voice"), ("outside_text_seen", "voice")):
        setattr(J._command_ctx, attr, True)
        out = J._execute_tool("settings", {"action": "set", "name": "wake word", "value": "1"}, "x")
        assert out.startswith("Refused"), attr
        setattr(J._command_ctx, attr, False)
    J._command_ctx.source = None  # scheduled/unattended run
    out = J._execute_tool("settings", {"action": "set", "name": "wake word", "value": "1"}, "x")
    assert out.startswith("Tool failed") and J._saved == {}
    J._command_ctx.source = "voice"
    J._command_ctx.hands_free = True  # follow-up window capture, not 'Hey Jarvis'
    out = J._execute_tool("settings", {"action": "set", "name": "wake word", "value": "1"}, "x")
    assert out.startswith("Tool failed") and J._saved == {}


def test_safe_mode_goes_through_its_own_rules(J, monkeypatch):
    calls = []
    monkeypatch.setattr(J, "set_safe_mode", lambda on, src=None: calls.append((on, src)) or "ok")
    J._execute_tool("settings", {"action": "set", "name": "safe mode", "value": "off"}, "safe mode off")
    assert calls == [(False, "voice")]


def test_email_started_runs_cannot_read_or_change_settings(J):
    J._command_ctx.untrusted_origin = True
    for name in ("settings", "stop_background_task"):
        assert J._untrusted_block(name)
    J._command_ctx.untrusted_origin = False
    J._command_ctx.outside_text_seen = True
    assert J._taint_block("settings") and J._taint_block("stop_background_task")


def test_stop_background_task(J, monkeypatch):
    class P:
        killed = False

        def kill(self):
            P.killed = True
    monkeypatch.setattr(J, "_finish_background_task", lambda *a, **k: None)
    J._RUNNING_BACKGROUND_PROCS.clear()
    J._RUNNING_BACKGROUND_PROCS[7] = (P(), 0.0)
    assert J._execute_tool("stop_background_task", {}, "stop it") == "Stopped task #7."
    assert P.killed
    assert J._execute_tool("stop_background_task", {"task_id": 7}, "stop 7").startswith("Tool failed")
    J._RUNNING_BACKGROUND_PROCS[1] = (P(), 0.0)
    J._RUNNING_BACKGROUND_PROCS[2] = (P(), 0.0)
    assert "ask the user which one" in J._execute_tool("stop_background_task", {}, "stop the task")
    J._RUNNING_BACKGROUND_PROCS.clear()


def test_narrowing_offers_the_new_tools(J):
    assert "settings" in J._narrowing_core("turn off the wake word")
    assert "stop_background_task" in J._narrowing_core("stop the research task")
    assert "settings" not in J._narrowing_core("what's the weather")


def test_pending_and_logs_pages(J, tmp_path):
    assert "pending" in J._dashboard_pages() and "logs" in J._dashboard_pages()
    out = J._execute_tool("dashboard_data", {"page": "pending"}, "anything waiting?")
    assert "Nothing is staged" in out
    out = J._execute_tool("dashboard_data", {"page": "logs", "query": "crash"}, "show crash log")
    assert "crash" in out
