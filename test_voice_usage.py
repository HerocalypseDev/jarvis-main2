"""Voice tab stats (jarvis_voice_usage + recording hooks + route). Temp DB only; no audio, no network."""

import sqlite3
import threading
import time

import numpy as np
import pytest

import jarvis_voice_usage as vu


def _db(tmp_path):
    path = tmp_path / "v.db"
    return (lambda: sqlite3.connect(path)), threading.Lock()


def test_summary_counts_lengths_engines_days_and_cache(tmp_path):
    connect, lock = _db(tmp_path)
    now = time.time()
    vu.record(connect, lock, "tts", "deepgram", "Hello there, how are you?", 1.5, now=now)
    vu.record(connect, lock, "tts", "deepgram", "Hi.", 0.4, cached=True, now=now)
    vu.record(connect, lock, "stt", "deepgram_stream", "what's the weather", 2.0, now=now)
    vu.record(connect, lock, "stt", "whisper", "", 0.5, now=now - 3 * 86400)
    s = vu.summary(connect, lock, now=now)
    t = s["periods"]["today"]["tts"]
    assert (t["chars"], t["words"], t["billed_chars"], t["cached_events"]) == (28, 6, 25, 1)
    assert s["periods"]["today"]["stt"]["chars"] == 18 and s["periods"]["week"]["stt"]["events"] == 2
    assert [e["engine"] for e in s["engines"]["stt"]] == ["deepgram_stream", "whisper"]
    assert s["daily"][-1]["tts_chars"] == 28 and s["daily"][-4]["stt_audio_s"] == 0.5
    assert s["records"]["tts"]["max_chars"] == 25 and s["busiest_day"]["date"] == s["daily"][-1]["date"]
    assert sum(h["tts"] + h["stt"] for h in s["hours"]) == 4


def test_old_rows_are_pruned(tmp_path):
    connect, lock = _db(tmp_path)
    now = time.time()
    vu.record(connect, lock, "tts", "piper", "old", 1, now=now - (vu.RETENTION_DAYS + 1) * 86400)
    vu.record(connect, lock, "tts", "piper", "new", 1, now=now)
    assert vu.summary(connect, lock, now=now)["periods"]["all_time"]["tts"]["events"] == 1


@pytest.fixture
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    import jarvis as j
    monkeypatch.setattr(j, "_record_voice", lambda kind, engine, text, audio_s, cached=False: j._record_voice_now(kind, engine, text, audio_s, cached))  # synchronous in tests
    return j


def test_transcription_and_synthesis_are_recorded_without_text(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_use_deepgram_stt", lambda: True)
    monkeypatch.setattr(jarvis.stt_deepgram, "transcribe", lambda mono, sr: "open my email please")
    assert jarvis.transcribe_pcm(np.zeros((16000, 1), dtype=np.float32), 16000) == "open my email please"
    monkeypatch.setattr(jarvis, "_use_deepgram_tts", lambda: True)
    monkeypatch.setattr(jarvis.tts_deepgram, "synthesize", lambda text: (b"\0\0" * 24000, 24000))
    monkeypatch.setattr(jarvis.cache, "enabled", lambda layer: False)
    jarvis._synthesize_and_cache("Your inbox has three new messages.")
    s = jarvis.voice_usage.summary(jarvis._memory_db_connect, jarvis._memory_db_lock)
    assert s["periods"]["today"]["stt"]["chars"] == 20 and s["periods"]["today"]["stt"]["audio_s"] == 1.0
    assert s["periods"]["today"]["tts"]["chars"] == 34 and s["periods"]["today"]["tts"]["audio_s"] == 1.0
    with jarvis._memory_db_lock:
        conn = jarvis._memory_db_connect()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(voice_usage)")]
        conn.close()
    assert "text" not in cols  # lengths only


def test_voice_usage_route(jarvis):
    from fastapi.testclient import TestClient
    client = TestClient(jarvis.dashboard._build_app(), base_url="http://127.0.0.1:8765")
    data = client.get("/api/voice_usage").json()
    assert set(data) >= {"periods", "engines", "daily", "hours", "weekdays", "records"} and len(data["daily"]) == 30
    assert client.get("/api/voice_usage", headers={"Host": "evil.example"}).status_code == 403
