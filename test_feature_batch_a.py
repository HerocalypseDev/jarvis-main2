"""Feature batch 2026-09-27, Phase A (FEATURES.md): clipboard history, Everything search, device names,
voice macros, battery saver, deadline context, and the generic /api/feature routes.
Temp DB only (JARVIS_MEMORY_DB_PATH); no real network, clipboard, battery or model calls."""

import json
import sqlite3
import threading
from datetime import datetime, timedelta

import pytest

import jarvis_battery as battery
import jarvis_clipboard_history as clip
import jarvis_everything as everything
import jarvis_macros as macros
import jarvis_netscan as netscan


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "t.db"
    return (lambda: sqlite3.connect(path)), threading.Lock()


@pytest.fixture
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "j.db"))
    import jarvis as j
    said = []
    monkeypatch.setattr(j, "queue_or_deliver_notification", lambda text, urgent=False, **k: said.append((text, urgent)))
    j._test_said = said
    return j


# --- A1 clipboard ------------------------------------------------------------------------------
@pytest.mark.parametrize("text,kind", [
    ("sk-ant-api03-abcdefghijklmnopqrstuvwxyz", "sensitive"),
    ("AKIAABCDEFGHIJKLMNOP", "sensitive"),
    ("Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123", "sensitive"),
    ("password: hunter22", "sensitive"),
    ("A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8", "sensitive"),
    ("https://example.com/page?x=1", "url"),
    ("def f(x):\n    return x\nclass A:\n    pass", "code"),
    ("TypeError: cannot read property 'foo' of undefined", "text"),
])
def test_clipboard_classify(text, kind):
    assert clip.classify(text) == kind


def test_clipboard_history_caps_dedupes_and_hides_secrets(db, monkeypatch):
    connect, lock = db
    monkeypatch.setattr(clip, "CLIP_MAX", 5)
    for i in range(8):
        clip.record(connect, lock, f"copy number {i}")
    clip.record(connect, lock, "copy number 3")  # re-copy: bumps to newest, no duplicate row
    assert clip.record(connect, lock, "sk-ant-api03-supersecretvalue123456") == "sensitive"
    items = clip.list_items(connect, lock, 50)
    assert len(items) == 5
    assert items[0]["kind"] == "sensitive" and items[0]["preview"] == ""
    assert items[1]["preview"] == "copy number 3"
    raw = connect().execute("SELECT text FROM clipboard_history WHERE kind='sensitive'").fetchone()
    assert raw == (None,)  # the secret itself is never stored
    sid = items[0]["id"]
    assert "can't be shown" in clip.handle_tool(connect, lock, {"action": "get", "id": sid})
    assert clip.search(connect, lock, "supersecret") == []
    assert clip.record(connect, lock, "__jarvis_sel_123__") is None  # Jarvis's own sentinel


def test_clipboard_search_and_get(db):
    connect, lock = db
    clip.record(connect, lock, "KeyError: 'user_id' in handler.py line 42")
    clip.record(connect, lock, "shopping list: eggs, milk")
    out = clip.handle_tool(connect, lock, {"action": "search", "query": "keyerror handler"})
    assert "KeyError" in out and "eggs" not in out
    copied = []
    iid = clip.search(connect, lock, "eggs")[0]["id"]
    assert "Put clipboard item" in clip.handle_tool(connect, lock, {"action": "get", "id": iid, "copy": True},
                                                    copied.append)
    assert copied == ["shopping list: eggs, milk"]


# --- A2 Everything -----------------------------------------------------------------------------
class _Resp:
    def __init__(self, body):
        self.body = body

    def read(self):
        return json.dumps(self.body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_everything_http_and_fallback(monkeypatch):
    urls = []

    def fake_open(url, timeout):
        urls.append(url)
        if ":80/" in url:
            raise OSError("refused")
        return _Resp({"totalResults": 1, "results": [{"type": "file", "name": "cv.pdf", "path": "C:\\Docs"}]})

    monkeypatch.delenv("JARVIS_EVERYTHING_URL", raising=False)
    monkeypatch.setattr(everything.urllib.request, "urlopen", fake_open)
    monkeypatch.setattr(everything, "_working_url", {"url": None, "checked": 0.0})
    r = everything.search("cv", ext="pdf")
    assert r["ok"] and r["backend"] == "http" and r["results"][0]["path"].endswith("cv.pdf")
    assert "ext%3Apdf" in urls[-1]
    assert "cv.pdf" in everything.format_results(r)

    monkeypatch.setattr(everything.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(everything, "_es", lambda q, c: None)
    r = everything.search("cv")
    assert not r["ok"] and "Everything" in r["error"]


def test_everything_refuses_non_loopback(monkeypatch):
    monkeypatch.setenv("JARVIS_EVERYTHING_URL", "http://10.0.0.5:80")
    called = []
    monkeypatch.setattr(everything.urllib.request, "urlopen", lambda *a, **k: called.append(a))
    monkeypatch.setattr(everything, "_es", lambda q, c: None)
    assert not everything.search("x")["ok"] and called == []


# --- A3 device names ---------------------------------------------------------------------------
def test_device_names_and_returning_devices(db):
    connect, lock = db
    scan = {"ok": True, "network_id": "gw", "devices": [
        {"ip": "192.168.1.5", "mac": "aa:bb:cc:dd:ee:01", "hostname": "pixel", "this_pc": False},
        {"ip": "192.168.1.9", "mac": "aa:bb:cc:dd:ee:02", "hostname": "", "this_pc": True}]}
    netscan.record(connect, lock, dict(scan), now=1000.0)
    out = netscan.handle_tool(connect, lock, {"action": "name", "device": "192.168.1.5", "name": "John's iPhone"}, scan)
    assert "John's iPhone" in out
    # Jarvis kept scanning (the phone was away, the PC wasn't), then the phone came back
    netscan.record(connect, lock, dict(scan, devices=scan["devices"][1:]), now=1000.0 + netscan.RETURN_AFTER_S)
    later = dict(scan)
    netscan.record(connect, lock, later, now=1000.0 + netscan.RETURN_AFTER_S + 5)
    netscan.apply_names(later, netscan.names(connect, lock))
    assert [d["name"] for d in later["returned"]][0] == "John's iPhone"
    assert netscan.describe(later["devices"][0]) == "John's iPhone (192.168.1.5)"
    assert "John's iPhone" in netscan.handle_tool(connect, lock, {"action": "named"}, later)
    assert "couldn't tell" in netscan.handle_tool(connect, lock, {"action": "name", "device": "nope", "name": "x"}, later)


def test_named_device_join_is_announced(jarvis, monkeypatch):
    netscan.set_name(jarvis._memory_db_connect, jarvis._memory_db_lock, "aa:bb:cc:dd:ee:01", "John's iPhone")
    result = {"ok": True, "network_id": "gw", "devices": [
        {"ip": "1.2.3.4", "mac": "aa:bb:cc:dd:ee:01", "hostname": "", "this_pc": False}]}
    monkeypatch.setattr(jarvis.netscan, "scan", lambda: dict(result))
    monkeypatch.setattr(jarvis.netscan, "record", lambda c, l, r, now=None: r.update(returned=r["devices"]) or [])
    jarvis._netscan_run()
    assert ("John's iPhone joined the network.", False) in jarvis._test_said


# --- A4 macros ---------------------------------------------------------------------------------
TOOLS = {"open_app", "system_action", "run_shell", "macros"}


def test_macro_validation(db):
    connect, lock = db
    assert "two words" in macros.save(connect, lock, "x", ["go"], [{"tool": "open_app", "input": {}}], TOOLS)
    assert "isn't an existing tool" in macros.save(connect, lock, "x", ["go now"], [{"tool": "nope"}], TOOLS)
    assert "isn't an existing tool" in macros.save(connect, lock, "x", ["go now"], [{"tool": "macros"}], TOOLS)
    assert macros.save(connect, lock, "work", ["Start work mode!"], [{"tool": "open_app", "input": {"app": "vscode"}}],
                       TOOLS).startswith("Saved")
    assert "already triggers" in macros.save(connect, lock, "other", ["start work mode"],
                                             [{"tool": "open_app", "input": {}}], TOOLS)


def test_macro_match_and_run_stops_at_staged_step(db):
    connect, lock = db
    macros.save(connect, lock, "leaving", ["I'm leaving"],
                [{"tool": "system_action", "input": {"system_action": "lock"}},
                 {"tool": "run_shell", "input": {"command": "shutdown /s"}},
                 {"tool": "open_app", "input": {"app": "x"}}], TOOLS)
    assert macros.match(connect, lock, "Jarvis, I'm leaving.")["name"] == "leaving"
    assert macros.match(connect, lock, "im leaving") is not None  # small transcription slip
    assert macros.match(connect, lock, "I'm leaving for the airport tomorrow at nine") is None
    ran = []

    def execute(tool, inp):
        ran.append(tool)
        return "That would shut down — staged, not run." if tool == "run_shell" else "ok"

    out = macros.run(connect, lock, macros.match(connect, lock, "i'm leaving"), execute, lambda r: "staged, not run" in r)
    assert ran == ["system_action", "run_shell"] and "needs your confirmation" in out
    macros.set_enabled(connect, lock, "leaving", False)
    assert macros.match(connect, lock, "i'm leaving") is None


def test_macro_runs_through_execute_tool_without_llm(jarvis, monkeypatch):
    calls = []
    monkeypatch.setattr(jarvis, "_execute_tool", lambda tool, inp, transcript, **k: calls.append((tool, inp)) or "Opened.")
    monkeypatch.setattr(jarvis, "run_agent_loop", lambda *a, **k: pytest.fail("macro must not call the LLM"))
    macros.save(jarvis._memory_db_connect, jarvis._memory_db_lock, "work", ["start work mode"],
                [{"tool": "open_app", "input": {"app": "vscode"}}], {"open_app"})
    assert jarvis._macro_reply("start work mode") == "Done: work."
    assert calls == [("open_app", {"app": "vscode"})]
    assert jarvis._macro_reply("what's the weather") is None


def test_macro_changes_refused_unattended(jarvis):
    jarvis._command_ctx.source = "phone"
    try:
        assert "only be changed from the PC" in jarvis._macros_tool({"action": "create", "name": "x"})
    finally:
        jarvis._command_ctx.source = None


# --- A5 battery --------------------------------------------------------------------------------
def test_battery_levels_and_once_per_crossing(monkeypatch):
    monkeypatch.setattr(battery, "_state", {"level": "ok"})
    assert battery.classify(50, False) == "ok"
    assert battery.classify(15, True) == "ok"  # plugged in
    assert battery.classify(None, None) == "ok"  # desktop
    assert battery.classify(18, False) == "low" and battery.classify(9, False) == "critical"
    assert "reducing background work" in battery.transition("low")
    assert battery.transition("low") is None
    assert "very low" in battery.transition("critical")
    assert battery.transition("critical") is None
    assert battery.transition("low") is None
    assert "back to normal" in battery.transition("ok")


def test_battery_tick_slows_autonomy_and_holds_speech(jarvis, monkeypatch):
    monkeypatch.setattr(battery, "_state", {"level": "ok"})
    monkeypatch.setattr(battery, "read", lambda: (8, False))
    monkeypatch.setattr(jarvis, "_log_action_audit", lambda *a: None)
    jarvis._battery_tick()
    assert battery.current() == "critical" and jarvis._test_said[-1][1] is True
    ticks = []
    monkeypatch.setattr(jarvis.autonomy, "tick", ticks.append)
    # "Long ago", not 0.0: time.monotonic() counts from boot, so on a machine up < 15 min 0.0 is "just now".
    monkeypatch.setattr(jarvis, "_battery_state", {"autonomy_last": -1e9})
    jarvis._autonomy_tick_battery_aware(datetime.now())
    jarvis._autonomy_tick_battery_aware(datetime.now())
    assert len(ticks) == 1  # second call within 15 min skipped
    assert battery.NETSCAN_FACTOR["critical"] == 0
    monkeypatch.setattr(battery, "_state", {"level": "ok"})


# --- A6 deadline context -----------------------------------------------------------------------
def test_deadline_nudge_includes_context(monkeypatch, tmp_path):
    import jarvis_autonomy as a
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "a.db"))
    monkeypatch.setattr(a, "_cb", {})
    notes = []
    a.configure({"deadline_context": lambda desc, bucket: f"ctx for {desc} ({bucket})",
                 "notify": lambda text, urgent=False: notes.append(text), "audit": lambda *x: None})
    seen = {}

    def fake_route(category, sender, desc, quote, action_type, details, conf, src, cid, **k):
        seen["text"] = details.get("text")
        return "act"

    monkeypatch.setattr(a, "_route", fake_route)
    monkeypatch.setattr(a, "dry_run", lambda: False)
    monkeypatch.setattr(a, "_set_commitment_meta", lambda *x, **k: None)
    monkeypatch.setattr(a, "_action_for_commitment", lambda c: (None, {}))
    due = (datetime.now() + timedelta(hours=10)).isoformat(timespec="seconds")
    monkeypatch.setattr(a, "_rows", lambda sql, args=(): [{"id": 1, "description": "send the tax report",
                                                          "deadline_iso": due, "source_quote": "", "meta": "{}"}])
    monkeypatch.setattr(a, "_meta", lambda c: {})
    a._deadline_scan(datetime.now(), True)
    assert "ctx for send the tax report (24h)" in seen["text"]


# --- generic dashboard routes --------------------------------------------------------------------
def test_feature_routes_and_host_guard(monkeypatch, tmp_path):
    import importlib
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "d.db"))
    import jarvis_dashboard as d
    importlib.reload(d)
    got = []
    d.providers["feature:demo"] = lambda action, payload: got.append((action, payload)) or {"ok": True}
    from fastapi.testclient import TestClient
    with TestClient(d._build_app(), base_url="http://127.0.0.1:8765") as c:
        assert c.get("/api/feature/demo").json() == {"ok": True}
        assert c.post("/api/feature/demo/name", json={"a": 1}).status_code == 200
        assert got[-1] == ("name", {"a": 1})
        assert c.post("/api/feature/demo/get", json={}).status_code == 400
        assert c.get("/api/feature/missing").status_code == 501
    with TestClient(d._build_app(), base_url="http://evil.example.com") as c:
        assert c.get("/api/feature/demo").status_code == 403
    with TestClient(d._build_app(), base_url="http://127.0.0.1:8765") as c:
        assert c.post("/api/feature/demo/name", json={}, headers={"Origin": "http://evil.example.com"}).status_code == 403
    d.providers.pop("feature:demo", None)
