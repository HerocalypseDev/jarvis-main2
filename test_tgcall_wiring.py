"""Telegram calls: the wiring inside jarvis.py (the gate on a call, history, messages while on a call, dashboard card).

The call module itself is tested in test_tgcall.py; nothing here rings anyone or touches a real Telegram account."""
import importlib
import re
import threading
from pathlib import Path

import pytest

import jarvis_tgcall as tg


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "wiring.db"))
    monkeypatch.setenv("JARVIS_TGCALL_DIR", str(tmp_path / "tgcall"))
    monkeypatch.setenv("JARVIS_ACK_PHRASES", "0")
    import jarvis as j
    monkeypatch.setattr(j, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(j.dashboard, "start_session", lambda *a, **k: 1)
    monkeypatch.setattr(j.dashboard, "end_session", lambda *a, **k: None)
    monkeypatch.setattr(j.dashboard, "notify", lambda *a, **k: None)
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    j._take_pending_action()
    tg.reset_for_tests()
    yield j
    j._take_pending_action()
    j._command_ctx.source = None
    j._command_ctx.hands_free = False
    tg.reset_for_tests()


# --- the catastrophic gate on a call ---------------------------------------------------------------------------------
def test_on_a_call_shutdown_stays_staged_and_a_spoken_yes_never_confirms(J, monkeypatch):
    """Through the REAL call wrapper and the REAL gate: only the model's reply is faked."""
    ran = []
    monkeypatch.setattr(J, "_execute_confirmed_action", lambda *a, **k: ran.append(a))
    monkeypatch.setattr(J, "run_agent_loop",
                        lambda t, **k: J._execute_tool("run_shell", {"command": "shutdown /s /t 0"}, t)
                        if "shut down" in t else "Okay.")                                   # what the model does
    J._tgcall_run_command("shut down the computer")
    assert J._pending_action is not None and J._pending_action["tool_name"] == "run_shell"
    assert J._pending_action["source"] == "phone"
    for said in ("yes", "yes please", "yeah"):
        out = J._tgcall_run_command(said)
        assert "push-to-talk" in out, said                 # refused, with the "use the key" message
        assert J._pending_action is not None, said          # still staged, never run
    assert ran == []
    J._tgcall_run_command("no, don't")                      # anything else drops it, and still nothing ran
    assert J._pending_action is None and ran == []


def test_the_confirmation_is_not_given_by_the_wrapper_itself(J, monkeypatch):
    """The wrapper must set hands_free for the duration of the command and restore it after."""
    seen = []
    monkeypatch.setattr(J, "handle_text_command",
                        lambda text, reply_sink=None, tone=None, source="text": seen.append(
                            (source, J._command_ctx.hands_free)) or reply_sink("ok"))
    J._command_ctx.hands_free = False
    J._tgcall_run_command("hello")
    assert seen == [("phone", True)] and J._command_ctx.hands_free is False


def test_nothing_from_a_call_command_is_spoken_on_the_pc_speakers(J, monkeypatch):
    spoken, kwargs = [], {}
    monkeypatch.setattr(J, "speak_text", lambda t: spoken.append(t))
    monkeypatch.setattr(J, "_speak_shaped", lambda t: spoken.append(t))
    monkeypatch.setattr(J, "run_agent_loop", lambda t, **k: kwargs.update(k) or "Found three cat pictures.")
    out = J._tgcall_run_command("search the web for cats and summarise the first page")
    assert out == "Found three cat pictures."
    assert kwargs.get("narrate") is False and spoken == []


def test_phone_limits_still_hold_on_a_call(J):
    """Attended-only tools are refused for a phone-source command, and a hands-free call can't restart or update Jarvis."""
    J._command_ctx.source = "phone"
    J._command_ctx.hands_free = True
    J._command_ctx.wake = False
    assert J._update_and_restart_reply("update and restart").startswith("To update and restart")
    assert not J._attended()


# --- history, audit row, journal ----------------------------------------------------------------------------------------
def test_each_call_leaves_one_history_row_one_audit_row_and_one_journal_line_without_private_text(J, monkeypatch):
    audit = []
    monkeypatch.setattr(J, "_log_action_audit", lambda *a: audit.append(a))
    res = tg.CallResult(True, "you said goodbye", 41.2, 3, direction="outgoing")
    J._tgcall_record(res, "outgoing")
    rows = J._tgcall_history(10)
    assert len(rows) == 1 and rows[0]["direction"] == "outgoing" and rows[0]["seconds"] == 41.2 and rows[0]["ok"] is True
    assert len(audit) == 1 and audit[0][0] == "telegram_call" and audit[0][1] == {"direction": "outgoing", "seconds": 41, "turns": 3}
    import jarvis_selfaware
    events = jarvis_selfaware.recent(10, subsystem="system", hours=1)
    mine = [e for e in events if e["kind"] == "call"]
    assert len(mine) == 1 and "outgoing Telegram call ended" in mine[0]["summary"]


def test_a_reason_with_secrets_is_masked_everywhere_it_is_stored(J):
    win_path = "C:" + "\\" + "Users" + "\\someone\\AppData\\Local\\Jarvis\\tgcall\\jarvis_call.session"   # built at runtime
    nasty = "PhoneNumberInvalid +2348012345678 key 0123456789abcdef0123456789abcdef at " + win_path
    J._tgcall_record(tg.CallResult(False, nasty, 0.0, 0, direction="outgoing"), "outgoing")
    stored = repr(J._tgcall_history(5))
    for secret in ("2348012345678", "0123456789abcdef", "someone", "AppData"):
        assert secret not in stored


def test_only_the_last_200_calls_are_kept(J):
    for i in range(205):
        J._tgcall_record(tg.CallResult(True, "x", 1.0, 0, direction="incoming"), "incoming")
    conn = J._memory_db_connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM tgcall_calls").fetchone()[0] == 200
    finally:
        conn.close()
    assert len(J._tgcall_history(10)) == 10


def test_one_inbox_line_per_call_and_a_second_request_while_busy_is_not_reported(J, monkeypatch):
    missed = []
    monkeypatch.setattr(J, "_add_missed", lambda text, source="": missed.append((text, source)))
    J._tgcall_done(tg.CallResult(False, "the spare account's login ended: run `python jarvis_tgcall.py login` again"))
    J._tgcall_done(tg.CallResult(True, "the other side hung up, declined, or Telegram ended the call (3.4 s after it was answered)", 4.0, 0))
    J._tgcall_done(tg.CallResult(False, "already on a call (or already ringing you)"))
    J._tgcall_inbound_done(tg.CallResult(True, "you said goodbye", 20.0, 2))
    assert len(missed) == 3 and all(src == "call" for _, src in missed)
    assert "didn't go through" in missed[0][0] and "3.4 s after it was answered" in missed[1][0]
    assert "You called me" in missed[2][0]


# --- on a call: messages go to the call or the inbox, never the PC speakers, never a second ring ----------------------------
class _FakeConv:
    def __init__(self):
        self._announcements = []


@pytest.fixture
def on_a_call(monkeypatch):
    monkeypatch.setattr(tg, "_line_busy", threading.Lock())
    tg._line_busy.acquire()
    conv = _FakeConv()
    tg._set_active(conv)
    yield conv
    tg._set_active(None)
    tg._line_busy.release()


def test_a_due_reminder_is_read_out_on_the_call_not_on_the_pc(J, monkeypatch, on_a_call):
    spoken, missed = [], []
    monkeypatch.setattr(J, "_notify_phone", lambda *a, **k: None)
    monkeypatch.setattr(J, "_speak_shaped", lambda t: spoken.append(t))
    monkeypatch.setattr(J, "speak_text", lambda t: spoken.append(t))
    monkeypatch.setattr(J, "_add_missed", lambda text, source="": missed.append((text, source)))
    J.queue_or_deliver_notification("Reminder: take the pasta off", is_reminder=True)
    assert on_a_call._announcements == ["Reminder: take the pasta off"] and spoken == [] and missed == []


def test_other_proactive_messages_wait_in_the_inbox_during_a_call(J, monkeypatch, on_a_call):
    spoken, missed, rang = [], [], []
    monkeypatch.setattr(J, "_notify_phone", lambda *a, **k: None)
    monkeypatch.setattr(J, "_speak_shaped", lambda t: spoken.append(t))
    monkeypatch.setattr(J, "_maybe_call_for_urgent", lambda t: rang.append(t))
    monkeypatch.setattr(J, "_add_missed", lambda text, source="": missed.append((text, source)))
    J.queue_or_deliver_notification("Your build finished.")
    J.queue_or_deliver_notification("Heads up: battery is low.", urgent=True)      # urgent: read on the call
    assert missed == [("Your build finished.", "call")]
    assert on_a_call._announcements == ["Heads up: battery is low."]
    assert spoken == [] and rang == []                                              # no PC speech, no second call


def test_with_no_active_conversation_an_urgent_alert_goes_to_the_inbox_not_the_speakers(J, monkeypatch):
    monkeypatch.setattr(tg, "_line_busy", threading.Lock())
    tg._line_busy.acquire()                                    # ringing, not yet answered: no conversation to read it on
    try:
        spoken, missed = [], []
        monkeypatch.setattr(J, "_notify_phone", lambda *a, **k: None)
        monkeypatch.setattr(J, "_speak_shaped", lambda t: spoken.append(t))
        monkeypatch.setattr(J, "_add_missed", lambda text, source="": missed.append((text, source)))
        J.queue_or_deliver_notification("Something urgent", urgent=True)
        assert spoken == [] and missed == [("Something urgent", "call")]
    finally:
        tg._line_busy.release()


def test_off_a_call_delivery_is_unchanged(J, monkeypatch):
    spoken = []
    monkeypatch.setattr(J, "_notify_phone", lambda *a, **k: None)
    monkeypatch.setattr(J, "_speak_shaped", lambda t: spoken.append(t))
    monkeypatch.setattr(J, "_maybe_call_for_urgent", lambda t: None)
    monkeypatch.setattr(J, "user_is_actively_working", lambda: False)
    J.queue_or_deliver_notification("Reminder: stretch", is_reminder=True)
    assert spoken == ["Reminder: stretch"]


def test_an_urgent_alert_never_rings_while_muted_or_on_a_call(J, monkeypatch):
    placed = []
    monkeypatch.setenv("JARVIS_TEST_ALLOW_CALLS", "1")
    monkeypatch.setattr(J, "_place_phone_call", lambda text: placed.append(text) or (True, "x"))
    monkeypatch.setattr(J.tgcall, "configured", lambda: True)
    monkeypatch.setattr(J, "_get_idle_seconds", lambda: 99999)
    monkeypatch.setattr(J.sleep_mode, "is_active", lambda: False)
    monkeypatch.setattr(J, "_is_muted", lambda: True)
    J._maybe_call_for_urgent("x")
    monkeypatch.setattr(J, "_is_muted", lambda: False)
    monkeypatch.setattr(J.tgcall, "on_call", lambda: True)
    J._maybe_call_for_urgent("x")
    assert placed == []


def test_the_pc_mic_features_are_off_during_a_call():
    """Wake word and the follow-up window would hear the room (and the owner's speakerphone) while on the phone."""
    src = Path(importlib.import_module("jarvis").__file__).read_text(encoding="utf-8")
    assert re.search(r"jarvis_wakeword\.enabled\(\) and not sleep_mode\.is_active\(\)\s*\n\s*and not tgcall\.on_call\(\)", src)
    assert "not safe_mode_on() and not tgcall.on_call():" in src
    assert "|call{int(tgcall.on_call())}" in src                 # a cached reply is never replayed across call state


# --- "call me": honest wording -------------------------------------------------------------------------------------------
def test_call_me_never_says_calling_before_it_is_ringing(J, monkeypatch):
    monkeypatch.setattr(J.tgcall, "configured", lambda: True)
    monkeypatch.setattr(J, "_place_phone_call", lambda text, asked=False: (True, "still connecting to Telegram (it can take a few seconds)"))
    out = J._send_to_my_phone_tool({"text": "hello", "channel": "call"})
    assert out.startswith("Still connecting") and "Calling you now" not in out
    monkeypatch.setattr(J, "_place_phone_call", lambda text, asked=False: (False, "the spare account's login ended"))
    assert J._send_to_my_phone_tool({"text": "hello", "channel": "call"}).startswith("Tool failed: the spare account's login ended")


# --- dashboard card, dashboard_data page, health, coverage --------------------------------------------------------------------
def test_the_calls_card_is_read_only_data_without_secrets(J, monkeypatch):
    monkeypatch.setenv("TGCALL_API_ID", "123456")
    monkeypatch.setenv("TGCALL_API_HASH_SECRET", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("TGCALL_TARGET", "@some_owner")
    J._tgcall_record(tg.CallResult(False, "no answer (the call rang out)", 0.0, 0, direction="outgoing"), "outgoing")
    card = J._FEATURE_PROVIDERS["calls"]("get", {})
    assert set(card) == {"status", "calls", "settings"} and card["calls"][0]["reason"].startswith("no answer")
    blob = repr(card)
    for secret in ("0123456789abcdef", "@some_owner", "123456"):
        assert secret not in blob


def test_dashboard_data_can_answer_when_did_i_last_call_you(J):
    J._tgcall_record(tg.CallResult(True, "you said goodbye", 12.0, 1, direction="incoming"), "incoming")
    out = J._dashboard_data_tool({"page": "calls"})
    assert "DASHBOARD PAGE 'calls'" in out and "incoming" in out and "you said goodbye" in out


def test_the_test_call_button_rings_through_the_normal_call_path(J, monkeypatch):
    placed = []
    monkeypatch.setattr(J, "_place_phone_call", lambda text, asked=False: placed.append(text) or (True, "ringing your Telegram now"))
    assert J._FEATURE_PROVIDERS["calls"]("test", {}) == {"ok": True, "message": "ringing your Telegram now"}
    assert placed and "test call" in placed[0]
    assert J._FEATURE_PROVIDERS["calls"]("delete", {}) is None


def test_the_calls_routes_sit_behind_the_dashboard_host_and_origin_guards(J):
    import jarvis_dashboard as d
    importlib.reload(d)
    d.providers["feature:calls"] = J._FEATURE_PROVIDERS["calls"]
    from fastapi.testclient import TestClient
    with TestClient(d._build_app(), base_url="http://127.0.0.1:8765", raise_server_exceptions=False) as c:
        assert c.get("/api/feature/calls").status_code == 200
        assert c.post("/api/feature/calls/test", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
    with TestClient(d._build_app(), base_url="http://evil.example.com") as c:
        assert c.get("/api/feature/calls").status_code == 403
        assert c.post("/api/feature/calls/test", json={}).status_code == 403


def test_health_card_shows_calls_once_configured(J, monkeypatch):
    monkeypatch.setattr(J.tgcall, "status", lambda: {"configured": True, "packages": "ok", "on_call": False, "listener_up": True,
                                                       "last": {"direction": "incoming", "seconds": 12, "reason": "you said goodbye"}})
    items = {i["name"]: i for i in J.health_report()["items"]}
    assert items["Calls"]["ok"] and "answering your calls" in items["Calls"]["detail"]
    monkeypatch.setattr(J.tgcall, "status", lambda: {"configured": True, "packages": "missing telethon (pip install x)", "on_call": False,
                                                       "listener_up": False, "last": None})
    items = {i["name"]: i for i in J.health_report()["items"]}
    assert not items["Calls"]["ok"] and "missing telethon" in items["Calls"]["detail"]


def test_the_doctor_reports_calls_only_once_set_up_has_started(monkeypatch, tmp_path):
    import jarvis_doctor as doc
    for k in ("TGCALL_API_ID", "TGCALL_API_HASH_SECRET", "TGCALL_TARGET"):
        monkeypatch.delenv(k, raising=False)
    assert doc.telegram_call_checks(doc.os.environ) == []                       # never started: nothing to nag about
    monkeypatch.setenv("TGCALL_API_ID", "123456")
    monkeypatch.setattr(tg, "packages_problem", lambda: "missing telethon (pip install x)")
    out = doc.telegram_call_checks(doc.os.environ)
    assert out and out[0]["status"] == "warn" and "telethon" in out[0]["detail"]
    monkeypatch.setattr(tg, "packages_problem", lambda: "")
    monkeypatch.setenv("JARVIS_TGCALL_DIR", str(tmp_path / "none"))
    out = doc.telegram_call_checks(doc.os.environ)
    assert out and out[0]["status"] == "warn" and "not finished" in out[0]["detail"]


# --- settings ---------------------------------------------------------------------------------------------------------------
def test_every_call_setting_is_in_the_settings_page_with_help_and_secrets_are_write_only():
    import jarvis_settings
    keys = {e["key"]: e for e in jarvis_settings.SETTINGS}
    src = Path("jarvis_tgcall.py").read_text(encoding="utf-8") + Path("jarvis.py").read_text(encoding="utf-8")
    used = set(re.findall(r"\b((?:JARVIS_)?TGCALL_[A-Z_]+|JARVIS_CALL[A-Z_]*)\b", src))
    for key in used:
        assert key in keys, f"{key} is read by the code but has no Settings entry"
        assert keys[key].get("help"), key
    assert jarvis_settings.is_secret("TGCALL_API_HASH_SECRET")


# --- "call me": no model round trip, honest words --------------------------------------------------------------------------
@pytest.mark.parametrize("said,expected", [
    ("call me", "call_me"), ("Ring me up please", "call_me"), ("hey jarvis, can you call me", "call_me"),
    ("phone me back now", "call_me"), ("please call me on telegram", "call_me"),
    ("call me Sam", "complex"), ("call me at nine tomorrow", "complex"), ("call me maybe", "complex"),
    ("remind me to call mum", "complex"),
])
def test_call_me_is_a_whole_utterance_intent(said, expected):
    import jarvis_latency
    assert jarvis_latency.classify_intent(said) == expected


def test_the_call_me_intent_says_what_really_happened(J, monkeypatch):
    seen = []
    monkeypatch.setattr(J, "_place_phone_call", lambda text, asked=False: seen.append((text, asked)) or (True, "ringing your Telegram now: pick up"))
    assert J._deterministic_intent_reply("call_me", "call me") == "Ringing your Telegram now: pick up."
    assert seen and seen[0][1] is True                       # the owner asked: the same-text-in-an-hour rule is not applied
    monkeypatch.setattr(J, "_place_phone_call", lambda text, asked=False: (False, "the spare account's login ended"))
    assert J._deterministic_intent_reply("call_me", "call me") == "I couldn't call you: the spare account's login ended."
    assert "call_me" in J._SLOW_INTENTS                       # runs after the dashboard session starts (it can wait up to 8 s)


def test_a_call_the_owner_asked_for_may_repeat_but_never_beats_the_daily_cap(J, monkeypatch):
    monkeypatch.setenv("JARVIS_CALLS_PER_DAY", "2")
    assert tg.reserve("Hi", repeat_ok=True) is None and tg.reserve("Hi", repeat_ok=True) is None
    assert "already made 2" in tg.reserve("Hi", repeat_ok=True)
    (tg.session_dir() / "calls.json").unlink()                 # a fresh day
    tg.reset_for_tests()
    assert tg.reserve("Alert") is None and "last hour" in tg.reserve("Alert")      # alerts keep the same-text rule


# --- Sleep Mode / Away mode / Guest rules ---------------------------------------------------------------------------------------
def test_an_urgent_alert_never_rings_in_sleep_mode_but_a_call_the_owner_asks_for_still_goes_out(J, monkeypatch):
    placed = []
    monkeypatch.setenv("JARVIS_TEST_ALLOW_CALLS", "1")
    monkeypatch.setattr(J, "_place_phone_call", lambda text, asked=False: placed.append((text, asked)) or (True, "ringing"))
    monkeypatch.setattr(J.tgcall, "configured", lambda: True)
    monkeypatch.setattr(J, "_get_idle_seconds", lambda: 99999)
    monkeypatch.setattr(J, "_is_muted", lambda: False)
    monkeypatch.setattr(J.sleep_mode, "is_active", lambda: True)
    J._maybe_call_for_urgent("the server is down")
    assert placed == []                                                       # asleep: no unprompted ring
    assert J._deterministic_intent_reply("call_me", "call me").startswith("Ringing")
    assert placed and placed[0][1] is True                                    # "call me" is the owner's own request


def test_the_call_module_knows_nothing_about_faces_sleep_or_the_owners_identity_beyond_the_chat_id():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(tg))
    imported = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | \
               {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not [m for m in imported if m and ("face" in m or "sleep" in m or "autonomy" in m)]


# --- one daily count for both kinds of call ----------------------------------------------------------------------------------
def test_callmebot_and_two_way_calls_share_one_saved_daily_count(J, monkeypatch):
    import io

    import jarvis_callmebot as cmb

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    opener = lambda req, timeout=None: Resp(b"Call queued")                            # noqa: E731
    monkeypatch.setenv("CALLMEBOT_TELEGRAM_USER", "@some_owner")
    monkeypatch.setenv("JARVIS_CALLS_PER_DAY", "2")
    assert cmb.call("one", opener=opener)[0] is True
    assert tg.reserve("two") is None                                                   # the two-way path sees the same count
    tg.reset_memory_only_for_tests()                                                   # a restart
    ok, what = cmb.call("three", opener=opener)
    assert ok is False and "already made 2" in what
