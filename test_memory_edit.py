"""Editable memory (P3): list/edit/forget facts, profile fields, forget_fact tool, dashboard routes.
Temp DB only (JARVIS_MEMORY_DB_PATH)."""

import pytest


@pytest.fixture
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    import jarvis as j
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    return j


def test_edit_keeps_history_and_forget_removes_every_version(jarvis):
    jarvis.remember_fact("preference", "likes tea")
    fid = jarvis.list_memory()["facts"][0]["id"]
    assert jarvis.edit_fact(fid, "likes green tea").startswith("Updated")
    new_id = jarvis.list_memory()["facts"][0]["id"]
    all_rows = jarvis.list_memory(include_superseded=True)["facts"]
    assert {f["content"] for f in all_rows} == {"likes tea", "likes green tea"}
    assert jarvis.edit_fact(fid, "again").startswith("No current fact")  # can't edit a replaced version
    assert "older version" in jarvis.forget_fact(new_id)
    assert jarvis.list_memory(include_superseded=True)["facts"] == []
    assert "#" in jarvis.recall_facts("") or jarvis.recall_facts("") == "No matching facts found."


def test_auto_extracted_facts_are_labelled(jarvis):
    jarvis.remember_fact("goal", "run a marathon", key="auto:marathon")
    jarvis.remember_fact("goal", "learn Rust")
    src = {f["content"]: f["source"] for f in jarvis.list_memory()["facts"]}
    assert src == {"run a marathon": "auto", "learn Rust": "remembered"}


def test_forget_fact_tool_is_attended_only(jarvis):
    jarvis.remember_fact("relationship", "Mum is mum@example.com")
    fid = jarvis.list_memory()["facts"][0]["id"]
    jarvis._command_ctx.source = "phone"
    try:
        out = jarvis._execute_tool_impl("forget_fact", {"id": fid}, "forget mum's email")
    finally:
        jarvis._command_ctx.source = None
    assert "from the PC" in str(out) and jarvis.list_memory()["facts"]
    jarvis._command_ctx.source = "voice"
    try:
        out = jarvis._execute_tool_impl("forget_fact", {"id": fid}, "forget mum's email")
    finally:
        jarvis._command_ctx.source = None
    assert "Forgot" in str(out) and jarvis.list_memory()["facts"] == []


def test_memory_routes(jarvis, monkeypatch):
    from fastapi.testclient import TestClient
    import jarvis_dashboard
    client = TestClient(jarvis_dashboard._build_app(), base_url="http://127.0.0.1:8765")
    assert client.post("/api/memory/facts", json={"category": "fact", "content": "has a cat"}).status_code == 200
    data = client.get("/api/memory").json()
    fid = data["facts"][0]["id"]
    assert data["facts"][0]["content"] == "has a cat" and "preference" in data["categories"]
    assert client.post(f"/api/memory/facts/{fid}", json={"content": "has two cats"}).json()["ok"]
    assert client.post("/api/memory/facts", json={"content": ""}).status_code == 400
    assert client.post("/api/memory/profile", json={"key": "home_town", "value": "Lagos"}).status_code == 200
    assert client.get("/api/memory").json()["profile"] == [{"key": "home_town", "value": "Lagos"}]
    # a page on another site can't erase memory
    new_id = client.get("/api/memory").json()["facts"][0]["id"]
    assert client.delete(f"/api/memory/facts/{new_id}", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.delete(f"/api/memory/facts/{new_id}").json()["ok"]
    assert client.delete("/api/memory/profile/home_town").json()["ok"]
    assert client.get("/api/memory").json() == {"categories": data["categories"], "facts": [], "profile": []}
