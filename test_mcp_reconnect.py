"""MCP servers that stop after connecting (2026-10-16, "my Windows MCP has been failing"): a crashed/ended server
stayed "connected" and every call answered "Connection closed" until Jarvis restarted. Uses a tiny real MCP server
over stdio, no Windows needed."""

import sys
import textwrap

import pytest

import jarvis

FAKE_SERVER = textwrap.dedent('''
    import os
    from mcp.server.mcpserver import MCPServer
    app = MCPServer("fake")

    @app.tool()
    def Ping() -> str:
        return "pong"

    @app.tool()
    def Die() -> str:
        os._exit(1)

    app.run()
''')


@pytest.fixture
def fake_server(tmp_path, monkeypatch):
    script = tmp_path / "fake_srv.py"
    script.write_text(FAKE_SERVER, encoding="utf-8")
    monkeypatch.setattr(jarvis, "_mcp_started", True)
    monkeypatch.setattr(jarvis, "_mcp_reconnect_tried", {})
    yield "fake", {"command": sys.executable, "args": [str(script)]}
    with jarvis._mcp_lock:
        jarvis._mcp_failed_servers.pop("fake", None)
        jarvis._mcp_handles.pop("fake", None)
        for name in [n for n, (srv, _r) in jarvis._mcp_tool_index.items() if srv == "fake"]:
            jarvis._mcp_tool_index.pop(name, None)
        jarvis._mcp_tool_schemas[:] = [t for t in jarvis._mcp_tool_schemas if not t["name"].startswith("mcp_fake_")]


def test_a_server_that_stops_is_reconnected_on_the_next_call(fake_server):
    name, cfg = fake_server
    assert jarvis._mcp_run_coro(jarvis._mcp_connect_one(name, cfg), 60)
    assert jarvis.execute_mcp_tool("mcp_fake_Ping", {}) == "pong"

    died = jarvis.execute_mcp_tool("mcp_fake_Die", {})
    assert "Connection closed" in died
    assert name in jarvis._mcp_failed_servers            # on the retry list, not "connected"
    assert jarvis._mcp_handles[name].error

    assert jarvis.execute_mcp_tool("mcp_fake_Ping", {}) == "pong"   # reconnected before the call
    assert name not in jarvis._mcp_failed_servers
    names = [t["name"] for t in jarvis._mcp_tool_schemas if t["name"].startswith("mcp_fake_")]
    assert sorted(names) == ["mcp_fake_Die", "mcp_fake_Ping"]      # no duplicate tool names after a reconnect


def test_dashboard_shows_a_stopped_server_as_failed(fake_server, monkeypatch):
    name, cfg = fake_server
    assert jarvis._mcp_run_coro(jarvis._mcp_connect_one(name, cfg), 60)
    jarvis.execute_mcp_tool("mcp_fake_Die", {})
    monkeypatch.setattr(jarvis, "_load_mcp_server_configs", lambda: {name: cfg})
    status = {s["name"]: s["status"] for s in jarvis._dashboard_get_services_status()}
    assert status[name] == "failed"


def test_error_text_names_the_real_cause_not_the_task_group():
    wrapped = ExceptionGroup("unhandled errors in a TaskGroup", [FileNotFoundError("uvx not found")])
    assert jarvis._mcp_error_text(wrapped) == "FileNotFoundError: uvx not found"
