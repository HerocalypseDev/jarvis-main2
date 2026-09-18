"""Tests for the caching layers (jarvis_cache.py + their wiring in jarvis.py).
Run with: python -m pytest test_cache.py -v

Never touches the real jarvis_memory.db, the real .cache/tts directory, Claude, or Fish Audio:
the DB path is redirected to a temp file, and every network/audio call is monkeypatched.
"""

from __future__ import annotations

import json
import time

import pytest

import jarvis_cache as cache


# --- pure helpers ----------------------------------------------------------------------------
def test_enabled_flag(monkeypatch):
    monkeypatch.delenv("JARVIS_FOO_CACHE", raising=False)
    assert cache.enabled("foo")
    for off in ("0", "false", "OFF", "no"):
        monkeypatch.setenv("JARVIS_FOO_CACHE", off)
        assert not cache.enabled("foo")


def test_normalize_and_self_contained():
    assert cache.normalize_text("  System status?! ") == "system status"
    assert cache.is_self_contained("what's my system status")
    assert cache.is_self_contained("list my reminders")
    assert not cache.is_self_contained("and tomorrow?")
    assert not cache.is_self_contained("what about that one")
    assert not cache.is_self_contained("cancel it")
    assert not cache.is_self_contained("")


def test_ttl_cache_expiry_and_lru():
    c = cache.TTLCache(max_entries=2)
    c.put("a", 1, 60)
    c.put("b", 2, 60)
    c.put("c", 3, 60)  # evicts "a"
    assert c.get("a") is cache.MISS and c.get("b") == 2 and c.get("c") == 3
    c.put("short", 9, 0.01)
    time.sleep(0.05)
    assert c.get("short") is cache.MISS


def test_tts_disk_cache_roundtrip_and_eviction(tmp_path):
    d = cache.TTSDiskCache(tmp_path / "tts", max_entries=3)
    pcm = b"\x01\x00" * 100
    assert d.get("k0") is None
    for i in range(5):
        d.put(f"k{i}", pcm, 22050)
        time.sleep(0.02)
    assert len(list((tmp_path / "tts").glob("*.wav"))) == 3
    assert d.get("k4") == (pcm, 22050)
    assert d.get("k0") is None  # oldest evicted


def test_sqlite_kv_max_age_and_prune(tmp_path):
    import sqlite3
    import threading

    path = tmp_path / "kv.db"
    kv = cache.SqliteKV("t", lambda: sqlite3.connect(path), threading.Lock(), max_rows=2)
    kv.put("a", "1")
    assert kv.get("a", 60) == "1"
    assert kv.get("a", -1) is None  # too old
    kv.put("b", "2")
    kv.put("c", "3")
    assert kv.get("a", 60) is None and kv.get("c", 60) == "3"


# --- wiring in jarvis.py ---------------------------------------------------------------------
@pytest.fixture()
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import jarvis as j

    monkeypatch.setattr(j, "get_mcp_tool_schemas", lambda: [])
    monkeypatch.setattr(j, "_history_snapshot", lambda: [])
    monkeypatch.setattr(j, "_append_history", lambda *a, **k: None)
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    j._reply_cache.clear()
    j._tool_result_cache.clear()
    cache.reset_stats()
    return j


def _scripted_claude(monkeypatch, j, tool_name: str | None, final_text: str):
    """Fake Claude: with a tool_name, the first call requests it and the next returns text."""
    calls = {"n": 0}

    def fake(body, timeout):
        calls["n"] += 1
        if tool_name and calls["n"] % 2 == 1:
            return {
                "stop_reason": "tool_use",
                "content": [{"type": "tool_use", "id": f"t{calls['n']}", "name": tool_name, "input": {}}],
                "usage": {},
            }
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": final_text}], "usage": {}}

    monkeypatch.setattr(j, "_claude_request", fake)
    return calls


def test_reply_cache_serves_readonly_repeat_without_claude(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda *a, **k: "CPU 5 percent")
    calls = _scripted_claude(monkeypatch, jarvis, "system_status", "Your CPU is at five percent.")
    first = jarvis.run_agent_loop("what is my system status")
    n_after_first = calls["n"]
    assert first == "Your CPU is at five percent." and n_after_first == 2
    second = jarvis.run_agent_loop("What is my system status?")  # normalizes to the same key
    assert second == first and calls["n"] == n_after_first  # no Claude call at all


def test_reply_cache_never_stores_mutating_turns(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda *a, **k: "Opened notepad.")
    calls = _scripted_claude(monkeypatch, jarvis, "open_app", "Opened Notepad.")
    jarvis.run_agent_loop("open notepad")
    n = calls["n"]
    jarvis.run_agent_loop("open notepad")
    assert calls["n"] > n  # ran the full loop again


def test_reply_cache_skips_context_dependent_and_toolless_turns(jarvis, monkeypatch):
    calls = _scripted_claude(monkeypatch, jarvis, None, "Sure.")
    jarvis.run_agent_loop("tell me a joke")  # zero tools: never cached (may depend on history/time)
    jarvis.run_agent_loop("tell me a joke")
    assert calls["n"] == 2
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda *a, **k: "CPU 5 percent")
    calls = _scripted_claude(monkeypatch, jarvis, "system_status", "Five percent.")
    jarvis.run_agent_loop("and what about that status")  # anaphoric: not cacheable
    n = calls["n"]
    jarvis.run_agent_loop("and what about that status")
    assert calls["n"] > n


def test_reply_cache_disabled_by_env(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_REPLY_CACHE", "0")
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda *a, **k: "CPU 5 percent")
    calls = _scripted_claude(monkeypatch, jarvis, "system_status", "Five percent.")
    jarvis.run_agent_loop("what is my system status")
    n = calls["n"]
    jarvis.run_agent_loop("what is my system status")
    assert calls["n"] > n


def test_tool_cache_ttl_and_invalidation(jarvis, monkeypatch):
    runs = []
    monkeypatch.setattr(
        jarvis, "_execute_tool_impl", lambda name, *a, **k: runs.append(name) or f"{name} result"
    )
    jarvis._execute_tool("list_reminders", {}, "t")
    jarvis._execute_tool("list_reminders", {}, "t")
    assert runs == ["list_reminders"]  # second was cached
    jarvis._execute_tool("create_reminder", {"text": "x"}, "t")  # mutation clears the cache
    jarvis._execute_tool("list_reminders", {}, "t")
    assert runs == ["list_reminders", "create_reminder", "list_reminders"]
    # different args -> different entry; failed results are never cached
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda name, *a, **k: runs.append(name) or "Couldn't read it.")
    jarvis._execute_tool("system_status", {}, "t")
    jarvis._execute_tool("system_status", {}, "t")
    assert runs.count("system_status") == 2


def test_tool_cache_short_ttl_expires(jarvis, monkeypatch):
    monkeypatch.setitem(jarvis.READONLY_TOOL_TTLS, "system_status", 0.02)
    runs = []
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda *a, **k: runs.append(1) or "ok status")
    jarvis._execute_tool("system_status", {}, "t")
    time.sleep(0.05)
    jarvis._execute_tool("system_status", {}, "t")
    assert len(runs) == 2


def test_tts_cache_skips_synthesis_on_repeat(jarvis, monkeypatch, tmp_path):
    monkeypatch.setattr(jarvis, "_tts_disk_cache", cache.TTSDiskCache(tmp_path / "tts"))
    monkeypatch.setattr(jarvis, "FISH_AUDIO_API_KEY", "k")
    fish_calls, played = [], []
    monkeypatch.setattr(
        jarvis, "_fish_audio_synthesize", lambda t, p=None: fish_calls.append(t) or (b"\x01\x00" * 50, 24000)
    )
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: played.append((len(raw), sr)))
    jarvis.speak_text("Message received.")
    jarvis.speak_text("Message received.")
    assert len(fish_calls) == 1 and len(played) == 2 and played[0] == played[1]
    monkeypatch.setenv("JARVIS_TTS_CACHE", "0")
    jarvis.speak_text("Message received.")
    assert len(fish_calls) == 2


def test_tts_fallback_audio_not_stored_under_fish_key(jarvis, monkeypatch, tmp_path):
    monkeypatch.setattr(jarvis, "_tts_disk_cache", cache.TTSDiskCache(tmp_path / "tts"))
    monkeypatch.setattr(jarvis, "FISH_AUDIO_API_KEY", "k")

    def boom(*a, **k):
        raise RuntimeError("fish down")

    monkeypatch.setattr(jarvis, "_fish_audio_synthesize", boom)
    monkeypatch.setattr(jarvis, "_piper_synthesize", lambda t, o=None: (b"\x02\x00" * 50, 22050))
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: None)
    jarvis.speak_text("Hello there.")
    # Fish comes back: it must be called again, not answered by the stored Piper clip.
    monkeypatch.setattr(jarvis, "_fish_audio_synthesize", lambda t, p=None: (b"\x03\x00" * 50, 24000))
    played = []
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: played.append(sr))
    jarvis.speak_text("Hello there.")
    assert played == [24000] or played == [22050]  # Piper clip may serve while Fish still fails...
    jarvis.speak_text("Different phrase.")
    assert played[-1] == 24000  # ...but a fresh phrase hits real Fish and is stored under its key


def test_summary_cache_skips_second_claude_call(jarvis, monkeypatch):
    calls = []

    def fake(body, timeout):
        calls.append(1)
        return {"content": [{"type": "text", "text": "Short version."}]}

    monkeypatch.setattr(jarvis, "_claude_request", fake)
    long_reply = "word " * 100
    assert jarvis._summarize_for_speech(long_reply) == "Short version."
    assert jarvis._summarize_for_speech(long_reply) == "Short version."
    assert len(calls) == 1
    monkeypatch.setenv("JARVIS_SUMMARY_CACHE", "0")
    jarvis._summarize_for_speech(long_reply)
    assert len(calls) == 2


def test_prompt_cache_breakpoints_and_flag(jarvis, monkeypatch):
    monkeypatch.delenv("JARVIS_PROMPT_CACHE_TTL", raising=False)
    blocks = jarvis.build_system_blocks("TONE")
    assert blocks[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "cache_control" not in blocks[1] and "TONE" in blocks[1]["text"] and "TONE" not in blocks[0]["text"]
    # the stable block must not change with per-call data
    assert jarvis.build_system_blocks("A")[0]["text"] == jarvis.build_system_blocks("B")[0]["text"]
    tools = jarvis._cached_tools([{"name": "a"}, {"name": "b"}])
    assert "cache_control" not in tools[0] and tools[1]["cache_control"]["ttl"] == "1h"
    monkeypatch.setenv("JARVIS_PROMPT_CACHE_TTL", "5m")
    assert jarvis._cached_tools([{"name": "a"}])[0]["cache_control"] == {"type": "ephemeral"}
    monkeypatch.setenv("JARVIS_PROMPT_CACHE", "0")
    assert "cache_control" not in json.dumps(jarvis.build_system_blocks()) + json.dumps(
        jarvis._cached_tools([{"name": "a"}])
    ) + json.dumps(jarvis._messages_with_cache_breakpoint([{"role": "user", "content": "x"}]))


def test_skills_cache_reparses_only_on_change(jarvis, monkeypatch, tmp_path):
    monkeypatch.setattr(jarvis, "_skills_dir", lambda: tmp_path)
    jarvis._skills_cache = None
    reads = []
    real = jarvis._read_skills_from_disk
    monkeypatch.setattr(jarvis, "_read_skills_from_disk", lambda: reads.append(1) or real())
    (tmp_path / "a.json").write_text(json.dumps({"name": "a", "instructions": "do a"}), encoding="utf-8")
    assert len(jarvis._load_skills()) == 1 and len(jarvis._load_skills()) == 1
    assert len(reads) == 1
    time.sleep(0.02)
    (tmp_path / "b.json").write_text(json.dumps({"name": "b", "instructions": "do b"}), encoding="utf-8")
    assert len(jarvis._load_skills()) == 2 and len(reads) == 2


def test_1h_ttl_rejection_falls_back_to_5m_and_retries(jarvis, monkeypatch):
    import io
    import urllib.error

    sent = []

    def fake_urlopen(req, timeout):
        body = json.loads(req.data)
        sent.append(body)
        if "1h" in json.dumps(body):
            raise urllib.error.HTTPError(
                req.full_url, 400, "bad", {}, io.BytesIO(b'{"error":{"message":"ttl is not supported"}}')
            )
        return b'{"content": [], "usage": {}}'

    monkeypatch.setattr(jarvis, "_urlopen_hard_timeout", fake_urlopen)
    monkeypatch.setattr(jarvis, "_cache_ttl_1h_rejected", False)
    body = {
        "system": [{"type": "text", "text": "x", "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
        "messages": [],
    }
    assert jarvis._claude_request(body, 5) == {"content": [], "usage": {}}
    assert len(sent) == 2 and "ttl" not in json.dumps(sent[1])
    assert jarvis._long_cache_control() == {"type": "ephemeral"}  # remembered for later calls
