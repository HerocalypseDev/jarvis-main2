"""Small, local-only cache helpers shared by jarvis.py: an env-flag reader, hit/miss counters, an
in-memory TTL+LRU cache, an on-disk TTS audio cache, and a tiny SQLite key/value cache.

Nothing here talks to the network or to Claude, and every helper is defensive — a cache failure
must degrade to "miss", never break a real command. Each layer is individually switchable with
an env var (JARVIS_<LAYER>_CACHE=0/false/off/no), default ON.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import sqlite3
import threading
import time
import wave
from collections import OrderedDict
from pathlib import Path
from typing import Callable

log = logging.getLogger("jarvis")

_FALSY = {"0", "false", "no", "off"}


def enabled(layer: str) -> bool:
    """JARVIS_<LAYER>_CACHE env flag, default on. Read on every call so it can be flipped in
    tests without re-importing."""
    return (os.environ.get(f"JARVIS_{layer.upper()}_CACHE") or "1").strip().lower() not in _FALSY


# --- hit/miss counters ---------------------------------------------------------------------
_stats_lock = threading.Lock()
_stats: dict[str, list[int]] = {}  # layer -> [hits, misses]


def record(layer: str, hit: bool, detail: str = "") -> None:
    with _stats_lock:
        counts = _stats.setdefault(layer, [0, 0])
        counts[0 if hit else 1] += 1
        h, m = counts
    log.info(
        "cache[%s] %s%s (%d/%d hits, %.0f%%)",
        layer, "HIT" if hit else "miss", f" {detail}" if detail else "", h, h + m, 100.0 * h / (h + m),
    )


def stats_snapshot() -> dict[str, dict]:
    with _stats_lock:
        return {k: {"hits": v[0], "misses": v[1]} for k, v in _stats.items()}


def reset_stats() -> None:
    with _stats_lock:
        _stats.clear()


# --- hashing / normalization ---------------------------------------------------------------
def stable_hash(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def normalize_text(text: str) -> str:
    """Lowercase, punctuation-stripped, whitespace-collapsed — so 'System status?' and
    'system status' share a cache entry."""
    t = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", t).strip()


# --- in-memory TTL + LRU -------------------------------------------------------------------
MISS = object()


class TTLCache:
    def __init__(self, max_entries: int = 256):
        self._max = max_entries
        self._lock = threading.Lock()
        self._data: OrderedDict[str, tuple[float, object]] = OrderedDict()

    def get(self, key: str):
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return MISS
            expires, value = item
            if expires <= time.monotonic():
                del self._data[key]
                return MISS
            self._data.move_to_end(key)
            return value

    def put(self, key: str, value, ttl_s: float) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + ttl_s, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


# --- reply cacheability --------------------------------------------------------------------
# A cached reply is replayed without Claude seeing the conversation history, so a command that
# only makes sense *given* that history ("and tomorrow?", "what about that one") must never be
# cached — the same words could mean something else next time.
_CONTEXT_DEPENDENT_RE = re.compile(
    r"\b(it|its|that|this|those|these|them|they|he|she|him|her|there|same|other|another|"
    r"previous|last|earlier|before|instead|also|too|more)\b|^(and|so|but|then|what about|how about)\b"
)


def is_self_contained(transcript: str) -> bool:
    norm = normalize_text(transcript)
    return bool(norm) and not _CONTEXT_DEPENDENT_RE.search(norm)


# --- TTS audio disk cache ------------------------------------------------------------------
class TTSDiskCache:
    """WAV files under one directory, keyed by hash. LRU by mtime (touched on every hit),
    capped by entry count and total bytes so the directory can never grow without bound."""

    def __init__(self, directory: Path, max_entries: int = 200, max_bytes: int = 100 * 1024 * 1024):
        self.dir = Path(directory)
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.wav"

    def get(self, key: str) -> tuple[bytes, int] | None:
        path = self._path(key)
        try:
            with self._lock:
                if not path.is_file():
                    return None
                os.utime(path, None)
                data = path.read_bytes()
            with wave.open(io.BytesIO(data), "rb") as wf:
                return wf.readframes(wf.getnframes()), wf.getframerate()
        except Exception as e:
            log.debug("TTS cache read failed (%s): %s", key[:8], e)
            return None

    def put(self, key: str, pcm: bytes, sample_rate: int) -> None:
        if not pcm:
            return
        try:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm)
            with self._lock:
                self.dir.mkdir(parents=True, exist_ok=True)
                tmp = self.dir / f"{key}.tmp"
                tmp.write_bytes(buf.getvalue())
                os.replace(tmp, self._path(key))
                self._evict_locked()
        except Exception as e:
            log.debug("TTS cache write failed (%s): %s", key[:8], e)

    def _evict_locked(self) -> None:
        files = sorted(self.dir.glob("*.wav"), key=lambda p: p.stat().st_mtime)  # oldest first
        total = sum(p.stat().st_size for p in files)
        while files and (len(files) > self.max_entries or total > self.max_bytes):
            victim = files.pop(0)
            try:
                total -= victim.stat().st_size
                victim.unlink()
            except OSError:
                pass


# --- tiny SQLite key/value cache (long-lived, survives restarts) ---------------------------
class SqliteKV:
    """key -> text value with a created_at timestamp; max_age_s is checked on read, and the
    table is pruned to max_rows on write. `connect` and `lock` are jarvis.py's existing
    _memory_db_connect/_memory_db_lock so this shares the one database and its WAL settings."""

    def __init__(self, table: str, connect: Callable[[], sqlite3.Connection], lock, max_rows: int = 500):
        self.table = table
        self._connect = connect
        self._lock = lock
        self._max_rows = max_rows
        self._ready = False

    def _ensure(self, conn: sqlite3.Connection) -> None:
        if not self._ready:
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table} "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL, created_at REAL NOT NULL)"
            )
            self._ready = True

    def get(self, key: str, max_age_s: float) -> str | None:
        try:
            with self._lock:
                conn = self._connect()
                try:
                    self._ensure(conn)
                    row = conn.execute(
                        f"SELECT value, created_at FROM {self.table} WHERE key = ?", (key,)
                    ).fetchone()
                finally:
                    conn.close()
        except Exception as e:
            log.debug("%s read failed: %s", self.table, e)
            return None
        if row and time.time() - row[1] <= max_age_s:
            return row[0]
        return None

    def put(self, key: str, value: str) -> None:
        try:
            with self._lock:
                conn = self._connect()
                try:
                    self._ensure(conn)
                    conn.execute(
                        f"INSERT OR REPLACE INTO {self.table} (key, value, created_at) VALUES (?, ?, ?)",
                        (key, value, time.time()),
                    )
                    conn.execute(
                        f"DELETE FROM {self.table} WHERE key NOT IN "
                        f"(SELECT key FROM {self.table} ORDER BY created_at DESC LIMIT ?)",
                        (self._max_rows,),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception as e:
            log.debug("%s write failed: %s", self.table, e)
