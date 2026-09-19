"""Tests for jarvis_restart.py. Run: python -m pytest test_restart.py -v
Never spawns a real helper or exits the test process: popen/exit_fn/sleep are faked."""

from __future__ import annotations

import threading

import jarvis_restart as rs


class _Proc:
    pid = 4242


def _proj(tmp_path, code="x = 1\n"):
    (tmp_path / "Jarvis.vbs").write_text("' launcher")
    (tmp_path / "jarvis.py").write_text(code)
    return tmp_path


def _run(tmp_path, busy=0, force=False, code="x = 1\n", speaking=None):
    calls = {"popen": [], "exit": [], "sleeps": []}

    def popen(cmd, **kw):
        calls["popen"].append(cmd)
        return _Proc()

    out = rs.restart(
        _proj(tmp_path, code), busy, force, speaking or threading.Event(),
        popen=popen, exit_fn=lambda c: calls["exit"].append(c),
        sleep=lambda s: calls["sleeps"].append(s), background=False,
    )
    return out, calls


def test_happy_path_spawns_helper_then_exits(tmp_path):
    out, calls = _run(tmp_path)
    assert "Restart scheduled" in out
    assert len(calls["popen"]) == 1 and calls["exit"] == [0]
    script = calls["popen"][0][-1]
    assert "Wait-Process" in script and "Jarvis.vbs" in script
    assert calls["sleeps"][0] == rs.MIN_DELAY_S  # lets the spoken reply happen first


def test_syntax_error_aborts_before_anything_is_stopped(tmp_path):
    out, calls = _run(tmp_path, code="def broken(:\n")
    assert "syntax error" in out and "jarvis.py" in out
    assert calls["popen"] == [] and calls["exit"] == []


def test_busy_background_tasks_refuse_unless_forced(tmp_path):
    out, calls = _run(tmp_path, busy=2)
    assert "background task" in out and calls["exit"] == []
    out, calls = _run(tmp_path, busy=2, force=True)
    assert "Restart scheduled" in out and calls["exit"] == [0]


def test_missing_launcher(tmp_path):
    (tmp_path / "jarvis.py").write_text("x=1\n")
    out = rs.restart(tmp_path, 0, False, threading.Event(), popen=None, exit_fn=None)
    assert "Jarvis.vbs is missing" in out


def test_waits_while_speaking_then_exits(tmp_path):
    speaking = threading.Event()
    speaking.set()
    n = {"i": 0}
    exits = []

    def sleep(s):
        n["i"] += 1
        if n["i"] == 4:
            speaking.clear()

    rs._stop_self(1, speaking, exits.append, sleep=sleep)
    assert exits == [0] and n["i"] >= 4


def test_tool_is_registered():
    import jarvis

    assert any(t["name"] == "restart_jarvis" for t in jarvis.AGENT_TOOLS)
