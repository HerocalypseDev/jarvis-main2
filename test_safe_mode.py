"""Safe mode + health card (P4). Temp DB and temp .env only."""

import pytest


@pytest.fixture
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("JARVIS_ENV_PATH", str(tmp_path / ".env"))
    monkeypatch.delenv("JARVIS_SAFE_MODE", raising=False)
    import jarvis as j
    monkeypatch.setattr(j.settings, "JARVIS_MODULE", None)
    monkeypatch.setattr(j.dashboard, "notify", lambda *a, **k: None)
    monkeypatch.setattr(j, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(j, "_session_context", {"pending_notifications": []})
    monkeypatch.setattr(j, "_save_session_context_locked", lambda: None)
    monkeypatch.setattr(j, "refresh_session_context", lambda: None)
    monkeypatch.setattr(j, "_notify_phone", lambda *a, **k: None)
    yield j
    import os
    os.environ.pop("JARVIS_SAFE_MODE", None)


def test_safe_mode_pauses_autonomy_followup_and_proactive_speech(jarvis, tmp_path, monkeypatch):
    spoken = []
    monkeypatch.setattr(jarvis, "_speak_shaped", lambda t: spoken.append(t))
    monkeypatch.setattr(jarvis.focus_mode, "should_suppress", lambda urgent: False)
    monkeypatch.setattr(jarvis.sleep_mode, "should_suppress", lambda urgent: False)
    monkeypatch.setattr(jarvis.sleep_mode, "is_active", lambda: False)
    monkeypatch.setattr(jarvis.face, "group_safe_suppress", lambda urgent: False)
    monkeypatch.setattr(jarvis, "user_is_actively_working", lambda: False)
    assert "on" in jarvis.set_safe_mode(True, "phone")  # turning it ON works from anywhere
    assert jarvis.safe_mode_on() and jarvis.autonomy.hard_disabled() and not jarvis.autonomy.enabled()
    assert "JARVIS_SAFE_MODE=1" in (tmp_path / ".env").read_text()
    jarvis.queue_or_deliver_notification("The build finished.")
    jarvis.queue_or_deliver_notification("Your timer is done.", urgent=True)
    assert spoken == ["Your timer is done."]  # urgent still speaks
    assert jarvis._session_context["pending_notifications"][0]["safe_mode"]
    assert "only be turned off from the PC" in jarvis.set_safe_mode(False, "phone")
    assert jarvis.safe_mode_on()
    assert "off" in jarvis.set_safe_mode(False, "voice")
    assert not jarvis.safe_mode_on() and not jarvis.autonomy.hard_disabled()


def test_no_followup_window_in_safe_mode(jarvis, monkeypatch):
    import numpy as np
    armed = []
    monkeypatch.setattr(jarvis, "transcribe_pcm", lambda *a, **k: "hello there")
    monkeypatch.setattr(jarvis.voice_tone, "analyze_tone", lambda *a, **k: {"tone": "neutral", "confidence": 1})
    monkeypatch.setattr(jarvis, "handle_text_command", lambda *a, **k: None)
    monkeypatch.setattr(jarvis.followup, "arm", lambda **k: armed.append(k))
    jarvis._handle_voice_command_impl(np.ones((10, 1), dtype=np.float32), 16000)
    jarvis.set_safe_mode(True, "voice")
    jarvis._handle_voice_command_impl(np.ones((10, 1), dtype=np.float32), 16000)
    assert len(armed) == 1


def test_safe_mode_voice_intent_is_deterministic(jarvis):
    assert jarvis._deterministic_intent_reply("safe_mode", "safe mode on").startswith("Safe mode is on")
    jarvis._command_ctx.source = "voice"
    try:
        assert "off" in jarvis._deterministic_intent_reply("safe_mode", "turn off safe mode")
    finally:
        jarvis._command_ctx.source = None
    assert jarvis._deterministic_intent_reply("safe_mode", "is safe mode on") == "Safe mode is off."


def test_health_report_and_routes(jarvis, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(jarvis, "_dashboard_get_pending", lambda: {"tool_name": "run_shell", "reason": "x"})
    h = jarvis.health_report()
    names = {i["name"]: i for i in h["items"]}
    assert not names["Confirmation"]["ok"] and "run_shell" in names["Confirmation"]["detail"]
    assert {"Brain", "Disk", "Autonomy", "Held messages"} <= set(names)
    client = TestClient(jarvis.dashboard._build_app(), base_url="http://127.0.0.1:8765")
    assert client.get("/api/health").json()["safe_mode"] is False
    assert client.post("/api/safe_mode", json={"on": True}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert "on" in client.post("/api/safe_mode", json={"on": True}).json()["result"]
    assert client.get("/api/health").json()["safe_mode"] is True
    client.post("/api/safe_mode", json={"on": False})  # the dashboard counts as "at the PC"
    assert not jarvis.safe_mode_on()
