"""Voice usage stats (2026-09-23): how much text Jarvis turns into speech (TTS) and how much of your
speech it transcribes (STT), per engine, for the dashboard's Voice tab.

One row per synthesized sentence / transcribed utterance in `voice_usage` (jarvis_memory.db):
counts only (characters, words, audio seconds, engine, cache hit), never the text itself. Rows older
than RETENTION_DAYS are pruned on write.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Callable

RETENTION_DAYS = 400


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS voice_usage (ts REAL NOT NULL, kind TEXT NOT NULL, "
                 "engine TEXT NOT NULL, chars INTEGER NOT NULL, words INTEGER NOT NULL, "
                 "audio_s REAL NOT NULL, cached INTEGER NOT NULL DEFAULT 0)")
    conn.execute("CREATE INDEX IF NOT EXISTS voice_usage_ts ON voice_usage (ts)")


def record(connect: Callable[[], sqlite3.Connection], lock, kind: str, engine: str, text: str,
           audio_s: float, cached: bool = False, now: float | None = None) -> None:
    """kind "tts" (Jarvis spoke `text`) or "stt" (the user said `text`); only its length is kept."""
    text = text or ""
    now = now or time.time()
    with lock:
        conn = connect()
        try:
            _ensure(conn)
            conn.execute("INSERT INTO voice_usage VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (now, kind, engine or "unknown", len(text), len(text.split()), round(float(audio_s), 3),
                          int(bool(cached))))
            conn.execute("DELETE FROM voice_usage WHERE ts < ?", (now - RETENTION_DAYS * 86400,))  # indexed, cheap
            conn.commit()
        finally:
            conn.close()


def summary(connect: Callable[[], sqlite3.Connection], lock, now: float | None = None, days: int = 30) -> dict:
    now = now or time.time()
    lt = time.localtime(now)
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    starts = {"today": midnight, "week": midnight - 6 * 86400,
              "month": time.mktime((lt.tm_year, lt.tm_mon, 1, 0, 0, 0, 0, 0, -1)), "all_time": 0.0}
    with lock:
        conn = connect()
        try:
            _ensure(conn)
            periods = {}
            for name, start in starts.items():
                p = {}
                for kind in ("tts", "stt"):
                    r = conn.execute(
                        "SELECT COUNT(*), COALESCE(SUM(chars),0), COALESCE(SUM(words),0), COALESCE(SUM(audio_s),0), "
                        "COALESCE(SUM(CASE WHEN cached=0 THEN chars ELSE 0 END),0), COALESCE(SUM(cached),0) "
                        "FROM voice_usage WHERE kind=? AND ts>=?", (kind, start)).fetchone()
                    p[kind] = {"events": r[0], "chars": r[1], "words": r[2], "audio_s": round(r[3], 1),
                               "billed_chars": r[4], "cached_events": r[5]}
                periods[name] = p
            since = midnight - (days - 1) * 86400
            engines = {k: [{"engine": e, "events": n, "chars": c, "audio_s": round(a, 1), "cached": h}
                           for e, n, c, a, h in conn.execute(
                               "SELECT engine, COUNT(*), SUM(chars), SUM(audio_s), SUM(cached) FROM voice_usage "
                               "WHERE kind=? AND ts>=? GROUP BY engine ORDER BY SUM(chars) DESC", (k, since))]
                       for k in ("tts", "stt")}
            rows = conn.execute("SELECT ts, kind, chars, audio_s, cached FROM voice_usage WHERE ts>=?", (since,)).fetchall()
            extremes = {k: conn.execute(
                "SELECT MAX(chars), MAX(audio_s), AVG(chars), AVG(audio_s) FROM voice_usage WHERE kind=? AND ts>=?",
                (k, since)).fetchone() for k in ("tts", "stt")}
        finally:
            conn.close()

    daily = []
    for i in range(days - 1, -1, -1):
        day_start = midnight - i * 86400
        daily.append({"date": time.strftime("%Y-%m-%d", time.localtime(day_start + 3600)),
                      "tts_chars": 0, "tts_billed_chars": 0, "stt_chars": 0, "tts_audio_s": 0.0, "stt_audio_s": 0.0})
    hours = [{"tts": 0, "stt": 0} for _ in range(24)]
    weekdays = [{"tts": 0, "stt": 0} for _ in range(7)]
    for ts, kind, chars, audio_s, cached in rows:
        idx = int((ts - (midnight - (days - 1) * 86400)) // 86400)
        if 0 <= idx < days:
            daily[idx][f"{kind}_chars"] += chars
            daily[idx][f"{kind}_audio_s"] += audio_s
            if kind == "tts" and not cached:
                daily[idx]["tts_billed_chars"] += chars  # actually sent to an engine (not a cache replay)
        t = time.localtime(ts)
        hours[t.tm_hour][kind] += 1
        weekdays[t.tm_wday][kind] += 1
    busiest = max(daily, key=lambda d: d["tts_chars"] + d["stt_chars"])
    avg = {k: {"max_chars": v[0] or 0, "max_audio_s": round(v[1] or 0, 1), "avg_chars": round(v[2] or 0, 1),
               "avg_audio_s": round(v[3] or 0, 1)} for k, v in extremes.items()}
    return {"periods": periods, "engines": engines, "daily": daily, "hours": hours, "weekdays": weekdays,
            "records": avg, "busiest_day": busiest if busiest["tts_chars"] + busiest["stt_chars"] else None,
            "days": days}
