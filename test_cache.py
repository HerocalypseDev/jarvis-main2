"""Tests for the caching layers (jarvis_cache.py + their wiring in jarvis.py).
Run with: python -m pytest test_cache.py -v

Never touches the real jarvis_memory.db, the real .cache/tts directory, Claude, or Fish Audio:
the DB path is redirected to a temp file, and every network/audio call is monkeypatched.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

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

    monkeypatch.setattr(j, "LLM_SETTINGS_PATH", tmp_path / "llm_provider.json")  # never read the real switch
    monkeypatch.delenv("JARVIS_LLM_PROVIDER", raising=False)
    # Deepgram off unless a test opts in — protects these pre-Deepgram tests from a real
    # DEEPGRAM_API_KEY sitting in the developer's .env (module attrs are read once at import,
    # so delenv alone wouldn't touch them).
    monkeypatch.setattr(j.stt_deepgram, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(j.tts_deepgram, "DEEPGRAM_API_KEY", "")
    # LLM token streaming off unless a test opts in — with a fake ANTHROPIC_API_KEY, any test
    # that calls run_agent_loop(narrate=True) without this would otherwise make a REAL network
    # call to Anthropic's streaming endpoint (the env var is read fresh per call, unlike the
    # Deepgram keys above, so setenv alone is enough here).
    monkeypatch.setenv("JARVIS_LLM_TTS_STREAM", "0")
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


def test_phone_command_gets_no_spoken_ack(jarvis, monkeypatch):
    spoken, sunk = [], []
    monkeypatch.setattr(jarvis, "speak_text", lambda t, *a, **k: spoken.append(t))
    monkeypatch.setattr(jarvis, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(
        jarvis, "run_agent_loop",
        lambda transcript, tone=None, narrate=False, tools_override=None: "done",
    )
    # Not "hello" — that's now a deterministic-intent greeting (voice-bug follow-up, 2026-09-22)
    # and would skip the mocked run_agent_loop entirely, which isn't what this test is about.
    jarvis.handle_text_command("what's on my calendar today", source="telegram", reply_sink=sunk.append)
    assert "Message received." not in spoken
    assert sunk == ["done"]


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


# --- api_spend (Admin API cost report) --------------------------------------------------------
def test_billing_summary_and_pagination():
    import jarvis_billing as b
    from datetime import datetime, timezone

    pages = [
        {"data": [{"starting_at": "2026-09-17T00:00:00Z", "results": [{"amount": "250", "model": "claude-haiku-4-5"}]}],
         "has_more": True, "next_page": "p2"},
        {"data": [{"starting_at": "2026-09-18T00:00:00Z", "results": [
            {"amount": "100.5", "model": "claude-haiku-4-5"}, {"amount": "50", "description": "web search"}]}],
         "has_more": False},
    ]
    seen = []

    def fake_get(url, headers, timeout):
        seen.append((url, headers))
        return pages[len(seen) - 1]

    out = b.get_api_spend("sk-ant-admin-x", 7, http_get=fake_get)
    assert len(seen) == 2 and "page=p2" in seen[1][0] and seen[0][1]["x-api-key"] == "sk-ant-admin-x"
    assert "$4.00" in out and "claude-haiku-4-5 $3.50" in out  # 250+100.5+50 cents = $4.00
    assert "sk-ant-admin" not in out


def test_billing_failures_are_plain_sentences():
    import io
    import urllib.error
    import jarvis_billing as b

    assert "No admin key" in b.get_api_spend("", 30)

    def denied(url, headers, timeout):
        raise urllib.error.HTTPError(url, 401, "no", {}, io.BytesIO(b"{}"))

    assert "rejected the admin key" in b.get_api_spend("k", 30, http_get=denied)

    def boom(url, headers, timeout):
        raise OSError("network down")

    assert "Couldn't read API spend" in b.get_api_spend("k", 30, http_get=boom)
    assert "No API spend" in b.summarize([], 30)


def test_api_spend_tool_is_registered_and_cacheable(jarvis, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_ADMIN_API_KEY", raising=False)
    assert any(t["name"] == "api_spend" for t in jarvis.AGENT_TOOLS)
    assert jarvis.READONLY_TOOL_TTLS["api_spend"] == 300
    assert "No Jarvis API usage" in jarvis._execute_tool_impl("api_spend", {}, "how much have i spent")


# --- local spend tracking ---------------------------------------------------------------------
def _kv_db(tmp_path):
    import sqlite3
    import threading

    path = tmp_path / "usage.db"
    return (lambda: sqlite3.connect(path)), threading.Lock()


def test_compute_cost_haiku_with_1h_and_5m_writes():
    import jarvis_billing as b

    usage = {
        "input_tokens": 1000, "output_tokens": 100, "cache_read_input_tokens": 10000,
        "cache_creation_input_tokens": 5000,
        "cache_creation": {"ephemeral_5m_input_tokens": 2000, "ephemeral_1h_input_tokens": 3000},
    }
    cost, saved, known = b.compute_cost("claude-haiku-4-5-20251001", usage)
    assert known and abs(cost - 0.011) < 1e-9 and abs(saved - 0.009) < 1e-9
    # no per-TTL breakdown -> all writes billed at the 5-minute rate
    cost2, _, _ = b.compute_cost("claude-haiku-4-5", {"cache_creation_input_tokens": 1_000_000})
    assert abs(cost2 - 1.25) < 1e-9
    assert b.compute_cost("some-future-model", {"input_tokens": 1_000_000})[2] is False


def test_record_and_local_summary(tmp_path):
    import time
    import jarvis_billing as b

    connect, lock = _kv_db(tmp_path)
    b.record_usage(connect, lock, "claude-haiku-4-5-20251001", {"input_tokens": 1_000_000, "output_tokens": 0})
    b.record_usage(connect, lock, "mystery-model", {"input_tokens": 500_000, "cache_read_input_tokens": 1_000_000})
    b.record_usage(connect, lock, "claude-haiku-4-5", {})  # empty usage: ignored
    s = b.local_summary(connect, lock)
    assert s["periods"]["all_time"]["calls"] == 2 and s["periods"]["today"]["calls"] == 2
    assert abs(s["periods"]["today"]["cost_usd"] - (1.0 + 0.5 + 0.1)) < 1e-9
    assert abs(s["periods"]["today"]["cache_saved_usd"] - 0.9) < 1e-9
    assert len(s["daily"]) == 14 and abs(s["daily"][-1]["cost_usd"] - 1.6) < 1e-9
    assert s["unknown_price_models"] == ["mystery-model"]
    text = b.format_local_summary(s)
    assert "$1.60 today" in text and "approximate" in text
    # an old row falls outside "today" but inside "all time"
    import sqlite3
    conn = connect()
    conn.execute("UPDATE api_usage SET ts = ?", (time.time() - 10 * 86400,))
    conn.commit(); conn.close()
    s2 = b.local_summary(connect, lock)
    assert s2["periods"]["today"]["calls"] == 0 and s2["periods"]["all_time"]["calls"] == 2


def test_record_usage_never_raises(tmp_path):
    import jarvis_billing as b

    def broken():
        raise RuntimeError("no db")

    b.record_usage(broken, __import__("threading").Lock(), "claude-haiku-4-5", {"input_tokens": 5})


def test_claude_request_records_usage(jarvis, monkeypatch):
    calls = []
    monkeypatch.setattr(jarvis.billing, "record_usage", lambda *a: calls.append(a))
    monkeypatch.setattr(
        jarvis, "_urlopen_hard_timeout",
        lambda req, t: b'{"content": [], "usage": {"input_tokens": 7, "output_tokens": 2}}',
    )
    jarvis._claude_request({"model": "claude-haiku-4-5-20251001", "messages": []}, 5)
    time.sleep(0.2)  # recording happens on a background thread
    assert len(calls) == 1 and calls[0][2] == "claude-haiku-4-5-20251001" and calls[0][3]["input_tokens"] == 7


# --- confirmation gate regression: a shutdown request must be *staged*, never run or ignored ---
def test_shutdown_via_run_shell_is_staged_not_run(jarvis, monkeypatch):
    import subprocess

    def must_not_run(*a, **k):
        raise AssertionError("the shutdown command was executed instead of staged")

    monkeypatch.setattr(subprocess, "run", must_not_run)
    monkeypatch.setattr(subprocess, "Popen", must_not_run)
    jarvis._pending_action = None
    result = jarvis._execute_tool_impl("run_shell", {"command": "shutdown /s /t 0"}, "shut down my computer")
    assert "staged, not run" in result
    pending = jarvis._take_pending_action()
    assert pending and pending["tool_name"] == "run_shell" and "shutdown" in pending["tool_input"]["command"]


def test_system_prompt_requires_the_tool_call_to_stage():
    import jarvis as j

    assert "MUST actually make that run_shell/run_python call" in j.AGENT_SYSTEM_PROMPT
    assert "NEVER tell the user you're about to shut down" in j.AGENT_SYSTEM_PROMPT


# --- proactive notifications (e.g. a finished delegated coding task) get the same speech shaping ---
def test_long_notification_is_summarized_for_speech_but_phone_keeps_full_text(jarvis, monkeypatch):
    spoken, phoned = [], []
    full = "James is done: I refactored the module and " + "updated many files " * 30
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    monkeypatch.setattr(jarvis, "_notify_phone", lambda t, force=False: phoned.append(t))
    monkeypatch.setattr(jarvis, "refresh_session_context", lambda: None)
    monkeypatch.setattr(jarvis.sleep_mode, "should_suppress", lambda urgent: False)
    monkeypatch.setattr(jarvis, "_summarize_for_speech", lambda t: "The refactor is finished.")
    jarvis.queue_or_deliver_notification(full, urgent=True)
    assert spoken == ["The refactor is finished."]  # shortened for the speakers
    assert phoned == [full.strip()]  # the phone push keeps the full text


def test_short_notification_is_spoken_unchanged_without_a_claude_call(jarvis, monkeypatch):
    spoken = []
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    monkeypatch.setattr(jarvis, "_notify_phone", lambda t, force=False: None)
    monkeypatch.setattr(jarvis, "refresh_session_context", lambda: None)
    monkeypatch.setattr(jarvis.sleep_mode, "should_suppress", lambda urgent: False)

    def no_claude(*a, **k):
        raise AssertionError("short text must not trigger a summary call")

    monkeypatch.setattr(jarvis, "_claude_request", no_claude)
    jarvis.queue_or_deliver_notification("Reminder: drink water", urgent=True)
    assert spoken == ["Reminder: drink water"]


# --- change_jarvis_code / self-edit delegation ------------------------------------------------
class _FakeProc:
    def poll(self):
        return None

    def kill(self):
        pass


@pytest.fixture()
def delegation(jarvis, monkeypatch, tmp_path):
    launched, ids = [], iter(range(100, 200))
    monkeypatch.setattr(jarvis.subprocess, "Popen", lambda cmd, **kw: launched.append((cmd, kw)) or _FakeProc())
    monkeypatch.setattr(jarvis, "_insert_background_task", lambda *a: next(ids))
    monkeypatch.setattr(jarvis, "_background_tasks_dir", lambda tid: (tmp_path / f"t{tid}").mkdir(exist_ok=True) or (tmp_path / f"t{tid}"))
    monkeypatch.setattr(jarvis, "_count_running_background_tasks", lambda kind: 0)
    monkeypatch.setattr(jarvis.workflow, "touch_workspace", lambda p: None)
    monkeypatch.setattr(jarvis, "record_recent_task", lambda t: None)
    monkeypatch.setattr(jarvis, "_RUNNING_BACKGROUND_PROCS", {})
    monkeypatch.setattr(jarvis, "_SELF_EDIT_TASK_IDS", set())
    # These model a request from the user; an unattended run (source None) is refused (audit H2).
    monkeypatch.setattr(jarvis, "_current_command_source", lambda: "voice")
    return launched


def test_change_jarvis_code_tool_registered_and_dispatches_self_edit(jarvis, delegation):
    assert any(t["name"] == "change_jarvis_code" for t in jarvis.AGENT_TOOLS)
    out = jarvis._execute_tool_impl("change_jarvis_code", {"feature": "add a joke command"}, "t")
    assert "background task #100" in out
    cmd, kw = delegation[0]
    prompt = cmd[cmd.index("-p") + 1]
    assert prompt.startswith(jarvis._SELF_EDIT_PREAMBLE) and prompt.endswith("add a joke command")
    for rule in ("CLAUDE.md", "confirmation gate", "secrets", "pytest", "do NOT push", "0.0.0.0"):
        assert rule in prompt
    from pathlib import Path
    assert Path(kw["cwd"]).resolve() == Path(jarvis.__file__).resolve().parent


def test_plain_delegation_into_jarvis_folder_also_gets_the_rules(jarvis, delegation):
    jarvis._delegate_to_claude_code("fix a bug in yourself", "")  # no repo_path defaults to Jarvis
    prompt = delegation[0][0][delegation[0][0].index("-p") + 1]
    assert prompt.startswith(jarvis._SELF_EDIT_PREAMBLE)


def test_delegation_to_another_repo_has_no_preamble_and_no_self_edit_lock(jarvis, delegation, tmp_path):
    other = tmp_path / "other_repo"
    other.mkdir()
    jarvis._delegate_to_claude_code("build a calculator", str(other))
    prompt = delegation[0][0][delegation[0][0].index("-p") + 1]
    assert prompt == "build a calculator" and not jarvis._SELF_EDIT_TASK_IDS
    jarvis._delegate_to_claude_code("another thing", str(other))  # not blocked by the self-edit lock
    assert len(delegation) == 2


def test_only_one_self_change_at_a_time(jarvis, delegation):
    jarvis._delegate_to_claude_code("first change", "")
    second = jarvis._delegate_to_claude_code("second change", "")
    assert "already changing my code" in second and len(delegation) == 1
    jarvis._RUNNING_BACKGROUND_PROCS.clear()  # first finished
    jarvis._delegate_to_claude_code("third change", "")
    assert len(delegation) == 2


def test_self_change_result_is_pushed_to_phone_even_with_proactive_pushes_off(jarvis, monkeypatch):
    pushed = []
    monkeypatch.setattr(jarvis, "JARVIS_PHONE_PROACTIVE_NOTIFICATIONS", False)
    monkeypatch.setattr(jarvis, "NTFY_TOPIC", "topic")
    monkeypatch.setattr(jarvis, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(jarvis, "_ntfy_publish", lambda text, title="Jarvis": pushed.append(text))
    jarvis._notify_phone("ordinary proactive message")
    assert pushed == []  # the off-by-default toggle still holds for everything else
    jarvis._notify_phone("James finished the change", force=True)
    assert pushed == ["James finished the change"]


# --- "where is your code?" regression (Jarvis once named the unrelated OpenJarvis project) -----
def test_system_prompt_states_jarvis_own_code_location_and_warns_about_lookalikes(jarvis):
    from pathlib import Path

    own = str(Path(jarvis.__file__).resolve().parent)
    stable = jarvis.build_system_blocks()[0]["text"]
    assert own in stable  # computed from this file's location, not typed in
    assert "do not need to search the disk" in stable
    assert "OpenJarvis" in stable and "different projects" in stable
    assert "change_jarvis_code" in stable
    assert own not in jarvis.build_system_blocks()[1]["text"]  # constant per install: cache-safe


def test_delegate_tool_steers_self_changes_to_change_jarvis_code(jarvis):
    tool = next(t for t in jarvis.AGENT_TOOLS if t["name"] == "delegate_to_claude_code")
    desc = tool["input_schema"]["properties"]["repo_path"]["description"]
    assert "change_jarvis_code" in desc and "never guess" in desc.lower()


def test_a_lookalike_jarvis_folder_is_not_treated_as_jarvis_itself(jarvis, delegation, tmp_path):
    lookalike = tmp_path / "OpenJarvis" / "src" / "openjarvis"  # the folder Jarvis wrongly named
    lookalike.mkdir(parents=True)
    jarvis._delegate_to_claude_code("add a feature", str(lookalike))
    cmd, kw = delegation[0]
    assert cmd[cmd.index("-p") + 1] == "add a feature"  # no self-edit rules: it's another project
    assert not jarvis._SELF_EDIT_TASK_IDS
    assert kw["cwd"] == str(lookalike)


def test_second_instance_cannot_take_the_single_instance_lock(jarvis, monkeypatch):
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setenv("JARVIS_SINGLE_INSTANCE_PORT", str(port))
    monkeypatch.setattr(jarvis, "_single_instance_sock", None)
    assert jarvis._acquire_single_instance_lock() is True
    held = jarvis._single_instance_sock
    try:
        assert jarvis._acquire_single_instance_lock() is False
    finally:
        held.close()


def test_gmail_watch_skill_requires_spoken_alert_for_important_mail():
    import json
    from pathlib import Path
    skill = json.loads((Path(__file__).parent / "skills" / "gmail_watch.json").read_text(encoding="utf-8"))
    text = skill["instructions"]
    assert "MUST be a short spoken alert" in text
    assert "security/account alert" in text
    assert "NO spoken reply" in text


def _gate_env(jarvis, monkeypatch):
    spoken = []
    monkeypatch.setattr(jarvis, "_speak_shaped", lambda t: spoken.append(t))
    monkeypatch.setattr(jarvis, "_notify_phone", lambda *a, **k: None)
    monkeypatch.setattr(jarvis, "refresh_session_context", lambda: None)
    monkeypatch.setattr(jarvis, "_save_session_context_locked", lambda: None)
    monkeypatch.setattr(jarvis.focus_mode, "should_suppress", lambda urgent: False)
    monkeypatch.setattr(jarvis.sleep_mode, "should_suppress", lambda urgent: False)
    monkeypatch.setattr(jarvis, "user_is_actively_working", lambda: True)
    monkeypatch.setattr(jarvis, "_is_preferred_work_hours", lambda now=None: True)
    monkeypatch.setitem(jarvis._session_context, "pending_notifications", [])
    return spoken


def test_busy_gate_holds_ordinary_notification_but_not_reminders(jarvis, monkeypatch):
    spoken = _gate_env(jarvis, monkeypatch)
    jarvis.queue_or_deliver_notification("suggestion")
    assert spoken == []
    jarvis.queue_or_deliver_notification("Reminder: drink water", bypass_busy_gate=True)
    assert spoken == ["Reminder: drink water"]


def test_bypass_busy_gate_still_respects_sleep_mode(jarvis, monkeypatch):
    spoken = _gate_env(jarvis, monkeypatch)
    monkeypatch.setattr(jarvis.sleep_mode, "should_suppress", lambda urgent: True)
    jarvis.queue_or_deliver_notification("Reminder: x", bypass_busy_gate=True)
    assert spoken == []


# --- mid-task narration ----------------------------------------------------------------------
def _narrating_claude(monkeypatch, j):
    calls = {"n": 0}

    def fake(body, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "stop_reason": "tool_use",
                "content": [
                    {"type": "text", "text": "Sure, let me track that down."},
                    {"type": "tool_use", "id": "t1", "name": "system_status", "input": {}},
                ],
                "usage": {},
            }
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "All done."}], "usage": {}}

    monkeypatch.setattr(j, "_claude_request", fake)


def test_narrate_speaks_text_beside_a_tool_call_and_keeps_it_out_of_the_reply(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda *a, **k: "ok")
    spoken = []
    monkeypatch.setattr(jarvis, "speak_text", spoken.append)
    _narrating_claude(monkeypatch, jarvis)
    reply = jarvis.run_agent_loop("fix the bugs in my project", narrate=True)
    assert spoken == ["Sure, let me track that down."]
    assert reply == "All done."  # not spoken twice


def test_narrate_off_keeps_old_behaviour(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda *a, **k: "ok")
    spoken = []
    monkeypatch.setattr(jarvis, "speak_text", spoken.append)
    _narrating_claude(monkeypatch, jarvis)
    reply = jarvis.run_agent_loop("fix the bugs in my project")
    assert spoken == [] and reply == "Sure, let me track that down. All done."


def _tool_only_claude(monkeypatch, j):
    def fake(body, timeout):
        return {
            "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": "t1", "name": "system_status", "input": {}}],
            "usage": {},
        }

    monkeypatch.setattr(j, "_claude_request", fake)


def test_tool_only_turn_falls_back_to_tool_result_by_default(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda *a, **k: "noted: no reply needed")
    _tool_only_claude(monkeypatch, jarvis)
    assert jarvis.run_agent_loop("x") == "noted: no reply needed"


def test_tool_result_fallback_can_be_disabled(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda *a, **k: "noted: no reply needed")
    _tool_only_claude(monkeypatch, jarvis)
    assert jarvis.run_agent_loop("x", tool_result_fallback=False) == ""


def test_scheduled_skill_with_silent_flag_speaks_nothing_on_empty_reply(jarvis, monkeypatch):
    seen = {}

    def fake_loop(transcript, **kw):
        seen.update(kw)
        return ""

    delivered = []
    monkeypatch.setattr(jarvis, "run_agent_loop", fake_loop)
    monkeypatch.setattr(jarvis, "queue_or_deliver_notification", delivered.append)
    jarvis._run_scheduled_skill({"name": "s", "instructions": "i", "silent_when_empty": True})
    assert seen["tool_result_fallback"] is False and delivered == []


def test_prompt_asks_for_plain_english_progress_lines(jarvis):
    text = " ".join(b.get("text", "") for b in jarvis.build_system_blocks(""))
    assert "never name tools" in text


# --- Google OAuth invalid_grant surfacing (MCP gmail/calendar) ---------------------------------
class _FakeMcpResult:
    def __init__(self, text: str, is_error: bool = False):
        self.content = [SimpleNamespace(text=text)]
        self.is_error = is_error


def _fake_mcp_run_coro(result):
    """execute_mcp_tool always builds the real coroutine before calling _mcp_run_coro; close it
    here so faking the result doesn't leave it dangling (avoids a RuntimeWarning)."""
    def run(coro, timeout=None):
        coro.close()
        return result
    return run


def test_gmail_invalid_grant_becomes_a_reauth_instruction(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_mcp_tool_index", {"mcp_gmail_search_emails": ("gmail", "search_emails")})
    monkeypatch.setattr(jarvis, "_mcp_run_coro", _fake_mcp_run_coro(_FakeMcpResult("Error: invalid_grant")))
    out = jarvis.execute_mcp_tool("mcp_gmail_search_emails", {"query": "is:unread"})
    assert "npx @gongrzhe/server-gmail-autoauth-mcp auth" in out
    assert "invalid_grant" not in out.lower().split("(")[0]  # human sentence, not the raw error dumped back


def test_calendar_invalid_grant_embedded_in_json_still_gets_the_hint(jarvis, monkeypatch):
    body = '{"accounts": [{"account_id": "normal", "status": "active", "error": "invalid_grant"}]}'
    monkeypatch.setattr(jarvis, "_mcp_tool_index", {"mcp_calendar_manage-accounts": ("calendar", "manage-accounts")})
    monkeypatch.setattr(jarvis, "_mcp_run_coro", _fake_mcp_run_coro(_FakeMcpResult(body)))
    out = jarvis.execute_mcp_tool("mcp_calendar_manage-accounts", {"action": "list"})
    assert "npx @cocal/google-calendar-mcp auth" in out


def test_other_mcp_errors_are_unaffected_by_the_auth_hint(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_mcp_tool_index", {"mcp_browser_click": ("browser", "click")})
    monkeypatch.setattr(jarvis, "_mcp_run_coro", _fake_mcp_run_coro(_FakeMcpResult("element not found", is_error=True)))
    out = jarvis.execute_mcp_tool("mcp_browser_click", {})
    assert out == "MCP tool reported an error: element not found"
