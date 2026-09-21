"""Regression tests for the 2026-09-21 audit fixes (C1, C2, H1-H4, M1, M3, L2).

Run: python -m pytest test_hardening.py -v
"""
from __future__ import annotations

import time

import pytest

import jarvis_workspace as ws


@pytest.fixture()
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import jarvis as j

    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(j, "_pending_action", None)
    return j


# --- C1: confirmation semantics ---------------------------------------------------------------
@pytest.mark.parametrize("text", ["yes", "Yes, do it.", "go ahead", "yeah sure", "confirmed", "please do"])
def test_clear_affirmatives_confirm(jarvis, text):
    assert jarvis._is_confirmation_yes(text)


@pytest.mark.parametrize(
    "text",
    [
        "No, don't do it", "please don't", "cancel that, don't go ahead", "I'm not sure",
        "that's incorrect", "yesterday I said stop", "yes but first tell me the weather in Paris please",
        "", "stop", "wait yes no",
    ],
)
def test_negations_and_long_sentences_do_not_confirm(jarvis, text):
    assert not jarvis._is_confirmation_yes(text)


def test_stale_pending_action_is_dropped_not_run(jarvis, monkeypatch):
    ran = []
    monkeypatch.setattr(jarvis, "_execute_confirmed_action", lambda *a, **k: ran.append(a))
    monkeypatch.setattr(jarvis, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(jarvis, "run_agent_loop", lambda *a, **k: "")
    monkeypatch.setattr(jarvis.dashboard, "start_session", lambda *a, **k: 1)
    monkeypatch.setattr(jarvis.dashboard, "end_session", lambda *a, **k: None)
    jarvis._pending_action = {
        "tool_name": "run_shell", "tool_input": {"command": "shutdown /s"}, "reason": "x",
        "queued_at": time.monotonic() - jarvis.PENDING_ACTION_TTL_S - 5,
    }
    jarvis._handle_text_command_impl("yes", None, {"tone": "neutral", "confidence": 0}, "voice")
    assert ran == [] and jarvis._pending_action is None


def test_staged_action_records_source_and_time(jarvis):
    jarvis._command_ctx.source = "phone"
    try:
        assert jarvis._queue_pending_confirmation("run_shell", {"command": "x"}, "r")
    finally:
        jarvis._command_ctx.source = None
    assert jarvis._pending_action["source"] == "phone" and "queued_at" in jarvis._pending_action
    jarvis._take_pending_action()


# --- H1: gate pattern matrix -------------------------------------------------------------------
CATASTROPHIC = [
    r"shutdown /s /t 0", r"shutdown /p", r"shutdown -r -t 0", r"shutdown /h", r"shutdown /l",
    r"wmic os where primary=1 call shutdown", r"(Get-WmiObject Win32_OperatingSystem).Win32Shutdown(5)",
    r"rundll32.exe powrprof.dll,SetSuspendState 0,1,0", "sh`utdown /s",
    r"format C: /q", r"Format-Volume -DriveLetter C", r"cipher /w:C:", r"bcdedit /delete {current}",
    r"reg delete HKLM\Software /f",
    r"Remove-Item C:\ -Recurse -Force", r"Remove-Item -Recurse -Force C:\ ", r"rd /s /q C:\ && echo x",
    r"rmdir /s /q %USERPROFILE%\Documents", "rm -rf ~/*", "rm -rf /", "rm -rf / --no-preserve-root; echo ok",
    r"Remove-Item -Recurse -Force $env:USERPROFILE\OneDrive", r"del /f /s /q C:\Users\USER\*",
    r"Remove-Item -Recurse -Force C:\Users\USER\Documents", r"Remove-Item -Recurse -Force C:\Users\USER",
    "shutil.rmtree('C:\\\\')", "shutil.rmtree(os.path.expanduser('~'))",
]
HARMLESS = [
    "rm -rf ./build", r"Remove-Item C:\Users\USER\proj\tmp -Recurse -Force", r"rd /s /q C:\proj\out",
    r"Get-ChildItem C:\ ", r"dir C:\Users", "python -m pytest", r"del C:\temp\a.txt",
    r"Remove-Item C:\Users\USER\OneDrive\Documents\x\y -Recurse", "echo hello",
]


@pytest.mark.parametrize("cmd", CATASTROPHIC)
def test_gate_catches(jarvis, cmd):
    assert jarvis._catastrophic_reason(cmd), cmd


@pytest.mark.parametrize("cmd", HARMLESS)
def test_gate_does_not_overreach(jarvis, cmd):
    assert jarvis._catastrophic_reason(cmd) is None, cmd


# --- H4: sensitive paths -----------------------------------------------------------------------
def test_reads_of_credentials_are_refused(jarvis, tmp_path):
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=secret-value-123")
    assert "Refused" in jarvis._read_file_tool(str(env))
    ok = tmp_path / "notes.txt"
    ok.write_text("hello")
    assert jarvis._read_file_tool(str(ok)) == "hello"


def test_writes_over_code_git_startup_and_env_are_refused(jarvis):
    code = ws._CODE_DIR
    for target in (code / "jarvis.py", code / ".env", code / ".git" / "config"):
        assert ws.resolve_write_path(str(target), "x")[0] is None, target
    startup = r"C:\Users\x\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\evil.bat"
    assert ws.resolve_write_path(startup, "x")[0] is None


def test_ordinary_writes_still_work(jarvis, tmp_path):
    p, why = ws.resolve_write_path(str(tmp_path / "a.txt"), "x")
    assert p is not None, why
    p2, why2 = ws.resolve_write_path("notes.txt", "x")  # relative -> workspace, not the code folder
    assert p2 is not None, why2


def test_http_request_refuses_private_hosts_and_secrets(jarvis, monkeypatch):
    assert "refused" in jarvis._http_request_tool("http://127.0.0.1:8765/api/command", "POST", None, "{}").lower()
    assert "refused" in jarvis._http_request_tool("http://169.254.169.254/latest", "GET", None, None).lower()
    monkeypatch.setattr(jarvis.image_download, "_check_host", lambda u: None)
    monkeypatch.setenv("SOME_API_KEY", "abcdef123456789")
    out = jarvis._http_request_tool("http://example.com/x", "POST", None, "leak abcdef123456789")
    assert "refused" in out.lower()


# --- H2: delegation ----------------------------------------------------------------------------
def test_delegate_child_env_is_an_allowlist(jarvis, monkeypatch):
    for k in ("GEMINI_API_KEY", "FISH_AUDIO_API_KEY", "TELEGRAM_BOT_TOKEN", "ANTHROPIC_ADMIN_API_KEY"):
        monkeypatch.setenv(k, "supersecretvalue")
    env = jarvis._delegate_child_env()
    assert not any("KEY" in k or "TOKEN" in k for k in env)
    assert "PATH" in env


def test_unattended_delegation_is_refused(jarvis):
    jarvis._command_ctx.source = None
    assert jarvis._delegate_to_claude_code("write a hello world", "").startswith("Refused")


# --- H3 / M3: attended-only configuration -------------------------------------------------------
def test_autonomy_tool_refuses_self_approval_when_unattended(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    import jarvis_autonomy as a

    for action in a.ATTENDED_ONLY_ACTIONS:
        for src in (None, "phone"):
            assert "only accepted" in a.handle_tool({"action": action, "id": 1}, src), (action, src)
    assert "only accepted" not in a.handle_tool({"action": "disable"}, None)


def test_organise_tool_refuses_config_changes_when_unattended(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    import jarvis_autonomy_organise as o

    for action in ("add_root", "add_rule", "remove_rule", "remove_root"):
        assert "only accepted" in o.handle_tool({"action": action, "path": "x", "name": "x"}, None)
        assert "only accepted" in o.handle_tool({"action": action, "path": "x", "name": "x"}, "phone")


# --- C2 / L2: dashboard guard on EVERY /api route -----------------------------------------------
def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "d.db"))
    import importlib

    import jarvis_dashboard as d

    importlib.reload(d)
    from fastapi.testclient import TestClient

    ran = []
    app = d._build_app(
        run_command=lambda text, sink: ran.append(text),
        approve_pending=lambda: ran.append("approved") or "ok",
        reject_pending=lambda: True,
        get_llm=lambda: {"provider": "claude"},
        set_llm=lambda p: ran.append("llm") or "Switched",
    )
    return TestClient(app, base_url="http://127.0.0.1:8765"), ran


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/command", {"text": "shutdown /s"}),
        ("post", "/api/pending/approve", None),
        ("post", "/api/pending/reject", None),
        ("post", "/api/llm", {"provider": "gemini"}),
        ("get", "/api/state", None),
        ("delete", "/api/sessions/finished", None),
    ],
)
def test_every_api_route_rejects_rebinding_and_cross_site(monkeypatch, tmp_path, method, path, body):
    c, ran = _client(monkeypatch, tmp_path)
    kw = {"json": body} if body is not None else {}
    with c:
        assert getattr(c, method)(path, headers={"host": "evil.example.com:8765"}, **kw).status_code == 403
        if method != "get":
            assert getattr(c, method)(path, headers={"origin": "https://evil.example.com"}, **kw).status_code == 403
            assert getattr(c, method)(path, headers={"origin": "null"}, **kw).status_code == 403
    time.sleep(0.05)
    assert ran == []


def test_same_origin_dashboard_calls_still_work(monkeypatch, tmp_path):
    c, ran = _client(monkeypatch, tmp_path)
    with c:
        r = c.post("/api/command", json={"text": "hi"}, headers={"origin": "http://127.0.0.1:8765"})
        assert r.status_code == 200
        assert c.post("/api/pending/approve", headers={"origin": "http://localhost:8765"}).status_code == 200
    time.sleep(0.1)
    assert "hi" in ran and "approved" in ran


def test_origin_parsing_is_strict():
    import jarvis_dashboard as d

    assert d._origin_is_loopback("http://127.0.0.1:8765")
    assert d._origin_is_loopback("http://[::1]:8765")
    assert not d._origin_is_loopback("http://localhost.evil.com")
    assert not d._origin_is_loopback("null")
    assert not d._origin_is_loopback("http://127.0.0.1.evil.com")
    assert d._host_is_loopback("localhost:8765") and not d._host_is_loopback("evil.com")
