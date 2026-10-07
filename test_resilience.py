"""Jarvis must not end because the microphone loop failed (owner: "jarvis keeps closing anyhow")."""

import pytest

import jarvis_resilience as r


def test_backoff_grows_then_caps():
    assert [r.backoff_seconds(n) for n in (0, 1, 2, 3, 4, 5, 9)] == [0.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]


def _run(fail_times, **kw):
    """Run supervise with a session that raises `fail_times` times and then stops normally."""
    calls = {"n": 0}
    events = []

    def session(started):
        calls["n"] += 1
        if calls["n"] <= fail_times:
            raise OSError("device unplugged")   # the microphone could not even be opened
        started()
        return None

    waits = []
    code = r.supervise(session, on_failure=lambda e, f, w: events.append(("fail", f, w)),
                       on_recovered=lambda f: events.append(("back", f)), sleep=waits.append, **kw)
    return code, calls["n"], events, waits


def test_a_failing_session_is_restarted_not_fatal():
    code, sessions, events, waits = _run(3)
    assert code == 0 and sessions == 4
    assert [e for e in events if e[0] == "fail"] == [("fail", 1, 2.0), ("fail", 2, 4.0), ("fail", 3, 8.0)]
    assert waits == [2.0, 4.0, 8.0]


def test_recovery_is_announced_once_per_outage():
    _, _, events, _ = _run(3)
    assert [e for e in events if e[0] == "back"] == [("back", 3)]


def test_no_announcement_when_nothing_failed():
    _, _, events, _ = _run(0)
    assert events == []


def test_ctrl_c_and_system_exit_still_stop_it():
    for exc in (KeyboardInterrupt, SystemExit):
        def session(started, exc=exc):
            raise exc()
        assert r.supervise(session, sleep=lambda s: None) == 0


def test_a_failure_in_the_failure_handler_cannot_end_it():
    n = {"n": 0}

    def session(started):
        n["n"] += 1
        if n["n"] == 1:
            raise RuntimeError("boom")

    def bad(*a):
        raise ValueError("handler broke")

    assert r.supervise(session, on_failure=bad, on_recovered=bad, sleep=lambda s: None) == 0 and n["n"] == 2


def test_a_long_healthy_session_resets_the_failure_count():
    clock = {"t": 0.0}
    seen = []
    n = {"n": 0}

    def session(started):
        n["n"] += 1
        started()
        if n["n"] == 1:
            clock["t"] += 5            # dies at once
            raise OSError("a")
        if n["n"] == 2:
            clock["t"] += 3600         # ran for an hour, then failed
            raise OSError("b")

    r.supervise(session, on_failure=lambda e, f, w: seen.append(f), sleep=lambda s: None,
                monotonic=lambda: clock["t"])
    assert seen == [1, 1]


def test_announcer_speaks_at_most_once_per_gap():
    t = {"t": 1000.0}
    a = r.Announcer(monotonic=lambda: t["t"])
    assert a.should_speak() is True
    t["t"] += 60
    assert a.should_speak() is False
    t["t"] += r.ANNOUNCE_GAP_S
    assert a.should_speak() is True


def test_crash_log_keeps_the_reason_and_stays_small(tmp_path):
    log = tmp_path / "crash.log"
    try:
        raise OSError("PortAudio: device unavailable")
    except OSError as e:
        r.write_crash(log, "microphone loop failed", e)
    text = log.read_text(encoding="utf-8")
    assert "microphone loop failed" in text and "device unavailable" in text and "Traceback" in text
    log.write_text("x" * (r.CRASH_LOG_MAX_BYTES + 10), encoding="utf-8")
    r.write_crash(log, "later entry")
    assert log.stat().st_size < r.CRASH_LOG_MAX_BYTES and "later entry" in log.read_text(encoding="utf-8")


def test_writing_the_crash_log_never_raises(tmp_path):
    r.write_crash(tmp_path / "no" / "such" / "dir" / "c.log", "x", ValueError("y"))


def test_main_runs_the_microphone_through_the_supervisor():
    import re
    src = open("jarvis.py", encoding="utf-8").read()
    body = src[src.index("\ndef main() -> int:"):]
    assert "jarvis_resilience.supervise(_listen_session" in body
    assert not re.search(r"except sd\.PortAudioError", body)   # that handler used to end the program
