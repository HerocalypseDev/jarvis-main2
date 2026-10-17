"""Two-way Telegram call (jarvis_tgcall): everything but the real Telegram line, which is faked."""
import asyncio
import queue
import threading
import time

import numpy as np
import pytest

import jarvis_tgcall as tg


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for k in ("TGCALL_API_ID", "TGCALL_API_HASH_SECRET", "TGCALL_TARGET", "CALLMEBOT_TELEGRAM_USER",
              "JARVIS_CALLS_PER_DAY", "JARVIS_TGCALL_MAX_MIN", "JARVIS_TGCALL_IDLE_S"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("JARVIS_TGCALL_DIR", str(tmp_path / "tgcall"))
    tg.reset_for_tests()
    yield
    tg.reset_for_tests()


def _configure(monkeypatch, tmp_path):
    monkeypatch.setenv("TGCALL_API_ID", "123456")
    monkeypatch.setenv("TGCALL_API_HASH_SECRET", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("TGCALL_TARGET", "@some_owner")
    d = tmp_path / "tgcall"
    d.mkdir(exist_ok=True)
    (d / "jarvis_call.session").write_bytes(b"x" * 10)


def _tone(seconds, amp=0.3, rate=tg.RATE):
    t = np.arange(int(seconds * rate)) / rate
    return tg.float_to_pcm16(amp * np.sin(2 * np.pi * 220 * t))


def _quiet(seconds):
    return b"\x00\x00" * int(seconds * tg.RATE)


# --- configuration -----------------------------------------------------------------------------------------------
def test_missing_lists_everything_then_nothing(monkeypatch, tmp_path):
    todo = tg.missing()
    assert len(todo) == 4 and not tg.configured()
    _configure(monkeypatch, tmp_path)
    assert tg.missing() == [] and tg.configured()


def test_config_validation(monkeypatch):
    monkeypatch.setenv("TGCALL_API_ID", "abc")
    assert tg.api_id() is None
    monkeypatch.setenv("TGCALL_API_HASH_SECRET", "nothex")
    assert tg.api_hash() == ""
    monkeypatch.setenv("TGCALL_TARGET", "some_owner")
    assert tg.target() == "@some_owner"
    monkeypatch.setenv("TGCALL_TARGET", "0801 234 5678")
    assert tg.target() == ""            # a local-format number is not a valid international number
    monkeypatch.setenv("TGCALL_TARGET", "+2348012345678")
    assert tg.target() == "+2348012345678"


def test_target_falls_back_to_the_callmebot_user(monkeypatch):
    monkeypatch.setenv("CALLMEBOT_TELEGRAM_USER", "@fallback_user")
    assert tg.target() == "@fallback_user"


def test_session_never_in_onedrive(monkeypatch):
    monkeypatch.setenv("JARVIS_TGCALL_DIR", r"C:\Users\x\OneDrive\jarvis")
    with pytest.raises(tg.CallError):
        tg.session_dir()
    assert tg.logged_in() is False


def test_numeric_settings_are_clamped(monkeypatch):
    monkeypatch.setenv("JARVIS_CALLS_PER_DAY", "9999")
    monkeypatch.setenv("JARVIS_TGCALL_MAX_MIN", "banana")
    assert tg.per_day() == 50 and tg.max_seconds() == 15 * 60


# --- caps ----------------------------------------------------------------------------------------------------------
def test_daily_cap_and_same_opening_and_refund(monkeypatch):
    monkeypatch.setenv("JARVIS_CALLS_PER_DAY", "2")
    assert tg.reserve("a") is None
    assert "last hour" in tg.reserve("a")
    assert tg.reserve("b") is None
    assert "already made 2" in tg.reserve("c")
    tg.refund("b")
    assert tg.reserve("c") is None


# --- audio helpers -------------------------------------------------------------------------------------------------
def test_tts_to_frames_is_20ms_frames_at_48k():
    raw = tg.float_to_pcm16(np.ones(16000, dtype=np.float32) * 0.1)   # 1 s at 16 kHz
    frames = tg.tts_to_frames(raw, 16000)
    assert all(len(f) == tg.FRAME_BYTES for f in frames)
    assert 49 <= len(frames) <= 51
    assert tg.tts_to_frames(b"", 16000) == []


def test_split_sentences_and_goodbye():
    assert tg.split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]
    assert all(len(s) <= 300 for s in tg.split_sentences("word, " * 200))
    assert tg.is_goodbye("ok bye") and tg.is_goodbye("that's all")
    assert not tg.is_goodbye("what is the goodbye song called by the beatles")


# --- listener ------------------------------------------------------------------------------------------------------
def test_listener_emits_one_utterance_after_silence():
    lis = tg.Listener()
    ev = lis.feed(_quiet(0.3) + _tone(1.0) + _quiet(1.0))
    kinds = [e[0] for e in ev]
    assert kinds == ["speech_start", "utterance"]
    audio = ev[1][1]
    assert audio.dtype == np.float32 and 0.9 < len(audio) / tg.STT_RATE < 2.2


def test_listener_ignores_noise_and_short_blips():
    lis = tg.Listener()
    assert lis.feed(_tone(0.1) + _quiet(1.2)) == []              # too short to start
    assert lis.feed(_tone(1.0, amp=0.003) + _quiet(1.0)) == []   # below the floor
    # a cough heard (0.28 s voiced) is a start but has too little voice to become an utterance
    ev = lis.feed(_tone(0.28) + _quiet(1.0))
    assert [e[0] for e in ev] == ["speech_start"]


def test_barge_in_needs_longer_speech_while_jarvis_talks():
    speaking = {"v": True}
    lis = tg.Listener(speaking=lambda: speaking["v"])
    assert lis.feed(_tone(0.35) + _quiet(1.0)) == []             # 0.35 s: "mhm", not a cut-in
    ev = lis.feed(_tone(0.7))
    assert ("speech_start",) in ev


def test_listener_handles_odd_chunk_sizes():
    lis = tg.Listener()
    data = _quiet(0.2) + _tone(1.0) + _quiet(1.0)
    ev = []
    for i in range(0, len(data), 777):
        ev += lis.feed(data[i:i + 777])
    assert [e[0] for e in ev] == ["speech_start", "utterance"]


# --- talker --------------------------------------------------------------------------------------------------------
def _frames(n):
    return [b"\x01\x00" * tg.FRAME_SAMPLES for _ in range(n)]


def test_talker_plays_everything():
    sent = []
    t = tg.Talker(sent.append, threading.Event(), sleep=lambda s: None)
    heard, cut, interrupted = t.say([("One.", lambda: _frames(3)), ("Two.", lambda: _frames(2))])
    assert (heard, cut, interrupted) == ("One. Two.", "", False)
    assert len(sent) == 5 and not t.speaking.is_set()


def test_talker_stops_within_a_frame_and_reports_what_was_heard():
    sent = []
    cancel = threading.Event()

    def send(fr):
        sent.append(fr)
        if len(sent) == 4:
            cancel.set()

    t = tg.Talker(send, cancel, sleep=lambda s: None)
    heard, cut, interrupted = t.say([("One.", lambda: _frames(3)), ("Two.", lambda: _frames(5)),
                                     ("Three.", lambda: _frames(2))])
    assert interrupted and heard == "One." and cut == "Two. Three."
    assert len(sent) == 4                                         # nothing more after the cut-in


def test_talker_survives_a_failed_synthesis():
    def boom():
        raise RuntimeError("tts down")

    sent = []
    t = tg.Talker(sent.append, threading.Event(), sleep=lambda s: None)
    heard, cut, interrupted = t.say([("Bad.", boom), ("Good.", lambda: _frames(2))])
    assert not interrupted and len(sent) == 2


# --- conversation --------------------------------------------------------------------------------------------------
class FakeTransport:
    def __init__(self, fail=None):
        self.frames: queue.Queue = queue.Queue()
        self.closed = threading.Event()
        self.sent: list = []
        self.started = False
        self.stopped = False
        self.fail = fail

    def start(self):
        if self.fail:
            raise tg.CallError(self.fail)
        self.started = True

    def send(self, fr):
        self.sent.append(fr)

    def stop(self):
        self.stopped = True
        self.closed.set()

    def say_to_jarvis(self, pcm):
        for i in range(0, len(pcm), tg.FRAME_BYTES):
            self.frames.put(pcm[i:i + tg.FRAME_BYTES])


def _hooks(replies, said_log, transcript="what time is it"):
    def run(said, note):
        said_log.append((said, note))
        return replies.pop(0) if replies else ""

    return tg.Hooks(transcribe=lambda audio: transcript,
                    synth=lambda text: (tg.float_to_pcm16(np.ones(1600, dtype=np.float32) * 0.1), 16000),
                    run_command=run)


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(tg.time, "sleep", lambda s: None)
    monkeypatch.setattr(tg.Talker, "__init__",
                        lambda self, send, cancel, clock=time.monotonic, sleep=lambda s: None:
                        _talker_init(self, send, cancel, clock, sleep))


def _talker_init(self, send, cancel, clock, sleep):
    self.send, self.cancel = send, cancel
    self.speaking = threading.Event()
    self._clock, self._sleep = clock, sleep
    self._say_lock = threading.Lock()


def test_unanswered_call_reports_and_does_not_start_talking(fast):
    tr = FakeTransport(fail="no answer (the call rang out)")
    res = tg.Conversation(tr, _hooks([], []), "Hello").run()
    assert not res.ok and "no answer" in res.reason and tr.stopped and tr.sent == []


def test_opening_then_question_answer_then_goodbye(fast, monkeypatch):
    log = []
    tr = FakeTransport()
    conv = tg.Conversation(tr, _hooks(["It is three o'clock."], log), "Hi, it's Jarvis.")
    bye = {"n": 0}

    def transcribe(audio):
        bye["n"] += 1
        return "what time is it" if bye["n"] == 1 else "ok bye"

    conv.hooks.transcribe = transcribe

    def caller():
        time.sleep(0.4)
        tr.say_to_jarvis(_quiet(0.2) + _tone(0.8) + _quiet(1.2))
        time.sleep(1.5)
        tr.say_to_jarvis(_tone(0.8) + _quiet(1.2))

    threading.Thread(target=caller, daemon=True).start()
    res = conv.run()
    assert res.ok and res.turns == 1 and "goodbye" in res.reason
    assert log == [("what time is it", "")]
    assert len(tr.sent) >= 2 and tr.stopped


def test_idle_call_ends_politely(fast, monkeypatch):
    monkeypatch.setenv("JARVIS_TGCALL_IDLE_S", "10")
    clock = {"t": 0.0}
    tr = FakeTransport()
    conv = tg.Conversation(tr, _hooks([], []), "", clock=lambda: clock["t"])
    orig_get = conv.utterances.get

    def tick(*a, **k):
        clock["t"] += 6
        return orig_get(*a, **{**k, "timeout": 0})

    conv.utterances.get = tick
    res = conv.run()
    assert res.ok and "nobody spoke" in res.reason


def test_max_length_ends_the_call(fast, monkeypatch):
    monkeypatch.setenv("JARVIS_TGCALL_MAX_MIN", "1")
    clock = {"t": 0.0}
    tr = FakeTransport()
    conv = tg.Conversation(tr, _hooks([], []), "", clock=lambda: clock["t"])
    orig_get = conv.utterances.get

    def tick(*a, **k):
        clock["t"] += 20
        conv._last_activity = clock["t"]
        return orig_get(*a, **{**k, "timeout": 0})

    conv.utterances.get = tick
    res = conv.run()
    assert "longest" in res.reason


def test_interruption_leaves_a_note_for_the_next_command(fast):
    tr = FakeTransport()
    conv = tg.Conversation(tr, _hooks([], []), "")

    def long_reply():
        conv.cancel_after = 3

    sent = []

    def send(fr):
        sent.append(fr)
        if len(sent) == 3:
            conv.cancel.set()

    conv.talker.send = send
    interrupted = conv.say("First sentence here. Second sentence here.")
    assert interrupted
    assert "did NOT hear" in conv._note and "Second sentence" in conv._note


def test_call_commands_run_hands_free_marker_is_the_hooks_job():
    """The module only passes text through run_command; jarvis.py wraps it with hands_free (see test below)."""
    import inspect
    assert "hands_free" not in inspect.getsource(tg)


# --- placing a call ------------------------------------------------------------------------------------------------
def test_call_owner_refuses_when_not_set_up():
    res = tg.call_owner("hi", _hooks([], []))
    assert not res.ok and "aren't set up" in res.reason


def test_call_owner_one_call_at_a_time_and_refund_on_no_answer(monkeypatch, tmp_path, fast):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("JARVIS_CALLS_PER_DAY", "1")
    res = tg.call_owner("hello", _hooks([], []), transport_factory=lambda: FakeTransport(fail="no answer"))
    assert not res.ok
    res2 = tg.call_owner("hello", _hooks([], []), transport_factory=lambda: FakeTransport(fail="no answer"))
    assert "already made" not in res2.reason          # the unanswered call was refunded
    assert tg._line_busy.acquire(blocking=False)
    try:
        assert tg.call_owner("x", _hooks([], [])).reason == "already on a call"
    finally:
        tg._line_busy.release()


def test_start_in_background_reports_done(monkeypatch, tmp_path, fast):
    _configure(monkeypatch, tmp_path)
    done = threading.Event()
    got = []
    ok, msg = tg.start_in_background("hello", _hooks([], []), on_done=lambda r: (got.append(r), done.set()),
                                     transport_factory=lambda: FakeTransport(fail="no answer"))
    assert ok and "ringing" in msg
    assert done.wait(5) and not got[0].ok


# --- explain -------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("exc,word", [
    (ImportError("No module named pytgcalls"), "aren't installed"),
    (RuntimeError("AuthKeyUnregistered"), "login ended"),
    (RuntimeError("USER_PRIVACY_RESTRICTED"), "Privacy"),
    (RuntimeError("FloodWaitError 30"), "slow down"),
    (TimeoutError("timed out"), "no answer"),
])
def test_explain_gives_plain_reasons(exc, word):
    assert word.lower() in tg.explain(exc).lower()


def test_module_holds_no_personal_data():
    import re
    src = open(tg.__file__, encoding="utf-8").read()
    assert not re.search(r"\+?234\d{9,}", src)
    assert not re.search(r"\b[0-9a-f]{32}\b", src)


def test_jarvis_call_command_is_a_hands_free_phone_command(monkeypatch, tmp_path):
    """The wiring in jarvis.py: a spoken 'yes' on a call must never confirm a staged action."""
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "m.db"))
    import jarvis
    seen = {}

    def fake(text, reply_sink=None, tone=None, source="text"):
        seen.update(text=text, source=source, hands=getattr(jarvis._command_ctx, "hands_free", None))
        reply_sink("It is noon.")

    monkeypatch.setattr(jarvis, "handle_text_command", fake)
    out = jarvis._tgcall_run_command("what time is it", "[Call: x] ")
    assert out == "It is noon."
    assert seen == {"text": "[Call: x] what time is it", "source": "phone", "hands": True}
    assert not getattr(jarvis._command_ctx, "hands_free", False)


def test_cli_reads_settings_from_the_dotenv_file(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text('﻿# c\nTGCALL_API_ID=123456\nexport TGCALL_API_HASH_SECRET="0123456789abcdef0123456789abcdef"\n'
                   'TGCALL_TARGET=@some_owner\n', encoding="utf-8")
    assert tg.api_id() is None
    assert tg.load_dotenv(env) == 3
    assert tg.api_id() == 123456 and tg.api_hash() and tg.target() == "@some_owner"


def test_dotenv_never_overrides_what_is_already_set(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("TGCALL_TARGET=@from_file\n", encoding="utf-8")
    monkeypatch.setenv("TGCALL_TARGET", "@already")
    assert tg.load_dotenv(env) == 0 and tg.target() == "@already"
    assert tg.load_dotenv(tmp_path / "missing.env") == 0


def test_calling_the_spare_account_itself_is_refused_clearly(monkeypatch, tmp_path):
    import asyncio
    import sys
    import types
    _configure(monkeypatch, tmp_path)

    class User:
        id = 777

    class Client:
        def __init__(self, *a, **k): pass
        async def connect(self): pass
        async def is_user_authorized(self): return True
        async def get_entity(self, to): return User()
        async def get_me(self): return User()

    tl = types.ModuleType("telethon"); tl.TelegramClient = Client
    pt = types.ModuleType("pytgcalls"); pt.PyTgCalls = object; pt.filters = object
    ty = types.ModuleType("pytgcalls.types")
    for n in ("AudioQuality", "CallConfig", "ChatUpdate", "Device", "Direction", "ExternalMedia", "MediaStream", "RecordStream"):
        setattr(ty, n, object)
    monkeypatch.setitem(sys.modules, "telethon", tl)
    monkeypatch.setitem(sys.modules, "pytgcalls", pt)
    monkeypatch.setitem(sys.modules, "pytgcalls.types", ty)
    monkeypatch.setattr(tg, "explain", lambda e: str(e), raising=False)
    t = tg.TelegramTransport("@some_owner")
    with pytest.raises(tg.CallError, match="spare account itself"):
        asyncio.run(t._connect())


# --- calls TO Jarvis ---------------------------------------------------------------------------------------------
def test_inbound_switch(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    assert tg.inbound_enabled()
    for v in ("0", "false", "off", "no"):
        monkeypatch.setenv("JARVIS_TGCALL_INBOUND", v)
        assert not tg.inbound_enabled()


def test_inbound_off_when_not_set_up(monkeypatch):
    assert not tg.inbound_enabled()
    assert tg.start_inbound(lambda: None) is False


def test_listener_answers_and_reports_then_stops(fast, monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(tg, "_inbound_thread", None)
    done = []
    made = []

    class Ringing(FakeTransport):
        def start(self):
            made.append(self)
            tg._inbound_stop.set()   # one call only
            super().start()

    res_seen = threading.Event()
    log = []
    hooks = lambda: _hooks([], log)  # noqa: E731

    def on_done(res):
        done.append(res)
        res_seen.set()

    # the caller hangs up straight after the greeting
    class Short(Ringing):
        def start(self):
            super().start()
            threading.Timer(0.3, self.stop).start()

    assert tg.start_inbound(hooks, on_done=on_done, transport_factory=Short)
    assert res_seen.wait(5) or made
    tg.stop_inbound()
    assert made and made[0].started and made[0].sent   # the greeting was spoken to the caller
    tg._inbound_stop.clear()


def test_listener_does_not_start_twice(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(tg, "_inbound_thread", None)
    monkeypatch.setattr(tg, "_inbound_stop", threading.Event())
    monkeypatch.setattr(tg, "_line_busy", threading.Lock())
    tg._line_busy.acquire()   # keeps the loop idle
    try:
        assert tg.start_inbound(lambda: None)
        assert tg.start_inbound(lambda: None) is False
    finally:
        tg.stop_inbound()
        tg._line_busy.release()


def test_inbound_transport_refuses_the_spare_account_as_target_and_other_callers(monkeypatch, tmp_path):
    src = open(tg.__file__, encoding="utf-8").read()
    # only the owner's chat id is ever answered, and a ring from anyone else is ignored
    assert "!= self._uid or self._incoming.is_set()" in src
    assert "hands_free" not in src


def test_outgoing_call_makes_the_listener_step_aside(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(tg, "_line_busy", threading.Lock())
    monkeypatch.setattr(tg, "_yield_line", threading.Event())
    monkeypatch.setattr(tg, "_inbound_listening", threading.Event())
    tg._inbound_listening.set()
    seen = []

    def release():
        for _ in range(100):
            if tg._yield_line.is_set():
                seen.append(True)
                tg._inbound_listening.clear()
                return
            time.sleep(0.01)

    threading.Thread(target=release, daemon=True).start()
    tr = FakeTransport(fail="no answer (the call rang out)")
    res = tg.call_owner("Hi", _hooks([], []), transport_factory=lambda: tr)
    assert seen and not res.ok
    assert not tg._yield_line.is_set() and not tg._line_busy.locked()


def test_listener_holds_the_session_from_the_moment_it_starts_connecting(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(tg, "_inbound_listening", threading.Event())
    seen = []

    class Slow(tg.InboundTransport):
        def _run(self):
            seen.append(tg._inbound_listening.is_set())   # the thread starts only after the flag is up
            self._error = "boom"
            self._ready.set()
            self.closed.set()

    tr = Slow("@x")
    with pytest.raises(tg.CallError):
        tr.start()
    assert seen == [True]
    assert not tg._inbound_listening.is_set()             # and it is released again on failure


def test_connecting_listener_is_cut_short_by_an_outgoing_call(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(tg, "_inbound_listening", threading.Event())

    class Never(tg.InboundTransport):
        def _run(self):
            time.sleep(0.5)                                # still "connecting"

    tr = Never("@x", should_stop=lambda: True)
    t0 = time.monotonic()
    with pytest.raises(tg.CallError):
        tr.start()
    assert time.monotonic() - t0 < 4
    assert not tg._inbound_listening.is_set()


def test_a_locked_session_is_retried_once(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(tg, "_line_busy", threading.Lock())
    monkeypatch.setattr(tg, "_yield_line", threading.Event())
    monkeypatch.setattr(tg, "_inbound_listening", threading.Event())
    monkeypatch.setattr(tg.time, "sleep", lambda s: None)
    made = [FakeTransport(fail="OperationalError: database is locked"), FakeTransport(fail="no answer (the call rang out)")]
    res = tg.call_owner("Hi", _hooks([], []), transport_factory=lambda: made.pop(0))
    assert not made and "rang out" in res.reason


def test_second_program_is_refused_while_another_holds_the_session(tmp_path, monkeypatch):
    """A running Jarvis keeps the spare account's session; the CLI test in another program must be refused with a
    plain message instead of hitting sqlite's "database is locked"."""
    import subprocess
    import sys
    import jarvis_tgcall as tg
    monkeypatch.setattr(tg, "_claimed", False)
    holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        guard = tg.session_dir() / tg._GUARD_NAME
        guard.parent.mkdir(parents=True, exist_ok=True)
        guard.write_text(f"{holder.pid}\nJarvis\n", encoding="utf-8")
        with pytest.raises(tg.CallError) as e:
            tg.claim_session("the call test")
        assert "in use by Jarvis" in str(e.value)
        assert str(holder.pid) in str(e.value)
    finally:
        holder.kill()
        holder.wait()


def test_a_session_left_by_an_exited_program_is_taken_over(tmp_path, monkeypatch):
    import jarvis_tgcall as tg
    monkeypatch.setattr(tg, "_claimed", False)
    monkeypatch.setattr(tg.atexit, "register", lambda *a, **k: None)
    guard = tg.session_dir() / tg._GUARD_NAME
    guard.parent.mkdir(parents=True, exist_ok=True)
    guard.write_text("999999\nJarvis\n", encoding="utf-8")        # no such process
    tg.claim_session("the call test")
    assert guard.read_text(encoding="utf-8").split("\n")[0] == str(tg.os.getpid())


def test_claim_is_taken_once_per_process_and_released_on_exit(tmp_path, monkeypatch):
    import jarvis_tgcall as tg
    monkeypatch.setattr(tg, "_claimed", False)
    monkeypatch.setattr(tg.atexit, "register", lambda *a, **k: None)
    tg.claim_session("Jarvis")
    tg.claim_session("Jarvis")                                     # same process: no refusal
    guard = tg.session_dir() / tg._GUARD_NAME
    assert guard.is_file()
    tg._release_session()
    assert not guard.exists()


def test_a_failed_send_records_why_the_call_dropped(monkeypatch):
    """A call that drops must say what ended it and how long after it was answered (the owner saw 3-4 s drops)."""
    import jarvis_tgcall as tg

    class BrokenLine:
        async def send_frame(self, uid, device, frame):
            raise RuntimeError("no media connection")

    class Device:
        MICROPHONE = "mic"

    loop = asyncio.new_event_loop()
    th = threading.Thread(target=loop.run_forever, daemon=True)
    th.start()
    try:
        tr = tg.TelegramTransport("@owner")
        tr._loop, tr._app, tr._uid, tr._device = loop, BrokenLine(), 1, Device
        tr._answered_at = time.monotonic() - 3.5
        tr.send(b"\x00" * tg.FRAME_BYTES)
        assert tr.closed.is_set()
        assert "sending audio failed" in tr.end_reason
        assert "3.5 s after it was answered" in tr.end_reason
        assert "no media connection" in tr.end_reason
    finally:
        loop.call_soon_threadsafe(loop.stop)
        th.join(timeout=5)


def test_the_first_reason_is_kept_when_several_things_end_the_call():
    import jarvis_tgcall as tg
    tr = tg.TelegramTransport("@owner")
    tr._end("Telegram reported that the call left the line (1.0 s after it was answered)")
    tr._end("sending audio failed later")
    assert tr.end_reason.startswith("Telegram reported that the call left the line")
    assert tr.closed.is_set()
