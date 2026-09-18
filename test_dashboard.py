"""QA regression suite for jarvis_dashboard.py. Run with: python -m pytest test_dashboard.py -v

Uses a temporary sqlite DB (via JARVIS_MEMORY_DB_PATH) so this never touches the real
jarvis_memory.db, and FastAPI's TestClient (real ASGI routing, real WebSocket handling —
not mocked HTTP).
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def db_path(monkeypatch, tmp_path):
    path = tmp_path / "test_jarvis_memory.db"
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(path))
    return path


@pytest.fixture()
def dashboard(db_path):
    import importlib
    import jarvis_dashboard as dashboard_module

    importlib.reload(dashboard_module)  # picks up the monkeypatched JARVIS_MEMORY_DB_PATH
    return dashboard_module


@pytest.fixture()
def client(dashboard):
    from fastapi.testclient import TestClient

    app = dashboard._build_app()
    with TestClient(app) as c:
        yield c


def test_state_shape_empty_db(client):
    r = client.get("/api/state")
    assert r.status_code == 200
    data = r.json()
    assert sorted(data.keys()) == sorted(
        ["pending_action", "sessions", "tasks", "audit", "victory_log", "counts", "metrics", "tool_names"]
    )
    assert data["pending_action"] is None
    assert data["sessions"] == []
    assert data["tasks"] == []
    assert data["metrics"] is None


def test_static_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "JARVIS" in r.text
    assert "metrics-strip" in r.text
    assert "tab-audit" in r.text
    assert "compose-form" in r.text


def test_static_assets_served(client):
    assert client.get("/app.js").status_code == 200
    assert client.get("/style.css").status_code == 200


def test_session_bookkeeping_round_trip(dashboard, client):
    sid = dashboard.start_session("voice", "hello jarvis")
    assert sid is not None
    dashboard.end_session(sid, "done", "hi there")

    r = client.get("/api/state")
    sessions = r.json()["sessions"]
    match = [s for s in sessions if s["id"] == sid]
    assert len(match) == 1
    assert match[0]["source"] == "voice"
    assert match[0]["status"] == "done"
    assert match[0]["reply"] == "hi there"


def test_end_session_with_none_id_is_noop(dashboard):
    dashboard.end_session(None, "done", "reply")  # must not raise


def test_pending_action_endpoints_501_when_not_wired(client):
    assert client.post("/api/pending/approve").status_code == 501
    assert client.post("/api/pending/reject").status_code == 501


def test_pending_action_approve_reject_wired(dashboard):
    from fastapi.testclient import TestClient

    calls = {"approved": 0, "rejected": 0}
    app = dashboard._build_app(
        get_pending=lambda: {"tool_name": "run_shell", "tool_input": {"command": "x"}, "reason": "y"},
        approve_pending=lambda: (calls.__setitem__("approved", calls["approved"] + 1), "ok")[1],
        reject_pending=lambda: (calls.__setitem__("rejected", calls["rejected"] + 1), True)[1],
    )
    with TestClient(app) as c:
        r = c.get("/api/state")
        assert r.json()["pending_action"]["tool_name"] == "run_shell"

        r = c.post("/api/pending/approve")
        assert r.status_code == 200 and r.json() == {"ok": True, "reply": "ok"}
        assert calls["approved"] == 1

        r = c.post("/api/pending/reject")
        assert r.status_code == 200 and r.json() == {"ok": True}
        assert calls["rejected"] == 1


def test_stop_task_501_when_not_wired(client):
    assert client.post("/api/tasks/bg-1/stop").status_code == 501


def test_stop_task_id_parsing(dashboard):
    from fastapi.testclient import TestClient

    killed = []
    app = dashboard._build_app(kill_background_task=lambda tid: killed.append(tid) or f"stopped {tid}")
    with TestClient(app) as c:
        r = c.post("/api/tasks/bg-42/stop")
        assert r.status_code == 200
        assert killed == [42]

        r = c.post("/api/tasks/tq-7/stop")
        assert r.status_code == 400

        r = c.post("/api/tasks/rem-3/stop")
        assert r.status_code == 400

        r = c.post("/api/tasks/bg-notanumber/stop")
        assert r.status_code == 400


def test_command_endpoint_501_when_not_wired(client):
    r = client.post("/api/command", json={"text": "do something"})
    assert r.status_code == 501


def test_command_endpoint_rejects_empty_text(dashboard):
    from fastapi.testclient import TestClient

    app = dashboard._build_app(run_command=lambda text, sink: None)
    with TestClient(app) as c:
        r = c.post("/api/command", json={"text": "   "})
        assert r.status_code == 400
        r = c.post("/api/command", json={})
        assert r.status_code == 400


def test_command_endpoint_invokes_run_command(dashboard):
    import threading
    from fastapi.testclient import TestClient

    received = {}
    done = threading.Event()

    def fake_run_command(text, sink):
        received["text"] = text
        sink("the reply")
        done.set()

    app = dashboard._build_app(run_command=fake_run_command)
    with TestClient(app) as c:
        r = c.post("/api/command", json={"text": "turn on the lights"})
        assert r.status_code == 200 and r.json() == {"ok": True}
        assert done.wait(timeout=5)
        assert received["text"] == "turn on the lights"


def test_audit_filters(dashboard, db_path):
    conn = sqlite3.connect(dashboard._db_path())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS action_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "timestamp TEXT NOT NULL, transcript TEXT NOT NULL, tool_name TEXT NOT NULL, "
        "tool_input TEXT NOT NULL, result TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO action_audit (timestamp, transcript, tool_name, tool_input, result) "
        "VALUES (?,?,?,?,?)",
        ("2020-01-01T00:00:00", "t1", "web_search", '{"q":"cats"}', "found cats"),
    )
    conn.execute(
        "INSERT INTO action_audit (timestamp, transcript, tool_name, tool_input, result) "
        "VALUES (?,?,?,?,?)",
        ("2020-01-02T00:00:00", "t2", "open_app", '{"app":"notepad"}', "Opened notepad."),
    )
    conn.commit()
    conn.close()

    from fastapi.testclient import TestClient

    app = dashboard._build_app()
    with TestClient(app) as c:
        r = c.get("/api/audit")
        assert len(r.json()["rows"]) == 2

        r = c.get("/api/audit", params={"tool_name": "web_search"})
        rows = r.json()["rows"]
        assert len(rows) == 1 and rows[0]["tool_name"] == "web_search"

        r = c.get("/api/audit", params={"q": "cats"})
        assert len(r.json()["rows"]) == 1

        r = c.get("/api/audit", params={"transcript": "t2"})
        assert len(r.json()["rows"]) == 1

        r = c.get("/api/audit", params={"date_from": "2020-01-02T00:00:00"})
        assert len(r.json()["rows"]) == 1

        r = c.get("/api/audit", params={"date_to": "2020-01-01T23:59:59"})
        assert len(r.json()["rows"]) == 1

        state = c.get("/api/state").json()
        assert set(state["tool_names"]) == {"web_search", "open_app"}


def test_metrics_passthrough(dashboard):
    from fastapi.testclient import TestClient

    fake_metrics = {"cpu": {"overall_percent": 12.0}}
    app = dashboard._build_app(get_system_status=lambda: fake_metrics)
    with TestClient(app) as c:
        r = c.get("/api/state")
        assert r.json()["metrics"] == fake_metrics


def test_metrics_callback_exception_does_not_break_state(dashboard):
    from fastapi.testclient import TestClient

    def boom():
        raise RuntimeError("psutil exploded")

    app = dashboard._build_app(get_system_status=boom)
    with TestClient(app) as c:
        r = c.get("/api/state")
        assert r.status_code == 200
        assert r.json()["metrics"] is None


def test_get_pending_exception_does_not_break_state(dashboard):
    from fastapi.testclient import TestClient

    def boom():
        raise RuntimeError("lock exploded")

    app = dashboard._build_app(get_pending=boom)
    with TestClient(app) as c:
        r = c.get("/api/state")
        assert r.status_code == 200
        assert r.json()["pending_action"] is None


def test_websocket_broadcast(dashboard):
    from fastapi.testclient import TestClient

    app = dashboard._build_app()
    with TestClient(app) as c:
        with c.websocket_connect("/ws") as ws:
            dashboard.notify({"type": "ping", "data": {"x": 1}})
            msg = ws.receive_json()
            assert msg == {"type": "ping", "data": {"x": 1}}


def test_notify_before_server_started_is_noop(dashboard):
    dashboard._broadcast_fn = None
    dashboard.notify({"type": "irrelevant"})  # must not raise
