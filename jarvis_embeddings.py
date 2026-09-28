"""Meaning-based memory retrieval (smarter batch, 2026-09-28).

Word matching (TF-IDF) picked facts that only shared filler words ("reminder", "tomorrow"), which is
how billing and sleep facts ended up read aloud as "Related: ...". Embeddings compare meaning:
"when is my ppm test" finds "The PPM exam is in room 4 on Friday", "message my sister" finds
"Racheal is Hero's sister".

- Provider: Gemini `gemini-embedding-001` (JARVIS_EMBED_MODEL), 256 dimensions, via the same key as the
  Gemini brain. Free on AI Studio.
- Cache: every embedded text is stored once in `embeddings` (sha256 of model+task+text -> float32 blob),
  so each fact is sent once; a command's own embedding is a single small request.
- Selection is relative, not an absolute cut-off (measured 2026-09-28: unrelated facts score ~0.62-0.70,
  real matches ~0.72-0.83, and the noise floor moves per query): a fact must score >= MIN_SCORE and
  stand MIN_GAP above the median score of all candidates, and (for a second pick) be within NEAR_TOP of
  the best one. Tuned on live scores: "wash clothes" vs the PPM-exam fact was 0.73 at median 0.664 (rejected),
  "message my sister" 0.725 at median 0.651 (kept).
- Any failure (no key, network, timeout) returns None and the caller falls back to TF-IDF. Circuit
  breaker: 3 failures in a row pause it for 5 minutes, so an outage never slows every command.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import threading
import time
import urllib.request
from statistics import median
from typing import Callable

DIMS = 256
MIN_SCORE = 0.70
MIN_GAP = 0.07
NEAR_TOP = 0.05  # a second pick must be this close to the best one
BATCH = 100
QUERY_TIMEOUT_S = 2.5
DOC_TIMEOUT_S = 15.0
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"

_breaker = {"fails": 0, "until": 0.0}
_breaker_lock = threading.Lock()


def model_name() -> str:
    return (os.environ.get("JARVIS_EMBED_MODEL") or "gemini-embedding-001").strip()


def _key() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()


def enabled(provider: str) -> bool:
    """JARVIS_EMBEDDINGS: auto (default: only while the Gemini brain is active, so memory text goes to the
    same vendor that already sees every prompt) | on | off. Always needs a Gemini key."""
    mode = (os.environ.get("JARVIS_EMBEDDINGS") or "auto").strip().lower()
    if mode in ("0", "off", "false", "no") or not _key():
        return False
    if mode in ("1", "on", "true", "yes"):
        return True
    return provider == "gemini"


def _pack(v: list[float]) -> bytes:
    return struct.pack(f"{len(v)}f", *v)


def _unpack(b: bytes) -> list[float]:
    return list(struct.unpack(f"{len(b) // 4}f", b))


def cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return num / den if den else 0.0


def _hash(text: str, task: str) -> str:
    return hashlib.sha256(f"{model_name()}|{DIMS}|{task}|{text}".encode()).hexdigest()


def init(connect: Callable, lock) -> None:
    with lock:
        conn = connect()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS embeddings (h TEXT PRIMARY KEY, vec BLOB NOT NULL, created_at TEXT)")
            conn.commit()
        finally:
            conn.close()


def _default_http(req: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _fetch(texts: list[str], task: str, timeout: float, http) -> list[list[float]]:
    body = {"requests": [{"model": f"models/{model_name()}", "content": {"parts": [{"text": t[:2000]}]},
                          "taskType": task, "outputDimensionality": DIMS} for t in texts]}
    req = urllib.request.Request(URL.format(model=model_name()), data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": _key(), "content-type": "application/json"})
    data = json.loads(http(req, timeout))
    return [e["values"] for e in data["embeddings"]]


_bg_fetch = threading.Lock()


def embed(connect: Callable, lock, texts: list[str], task: str = "RETRIEVAL_DOCUMENT",
          timeout: float = DOC_TIMEOUT_S, http=None, cached_only: bool = False,
          store: bool = True) -> list[list[float]] | None:
    """Vectors for `texts` (cached), or None on any failure.
    cached_only: never fetch on the caller's thread - if anything is missing, start ONE background fetch and
    return None (the caller falls back to TF-IDF this time). Used on the command path (audit 2026-09-28: a
    fact added mid-session made the next command wait up to 15 s for its embedding).
    store=False: don't keep the vectors (per-command queries; caching every command grew the table forever)."""
    now = time.time()
    with _breaker_lock:
        if _breaker["until"] > now:
            return None
    http = http or _default_http
    try:
        init(connect, lock)
        hashes = [_hash(t, task) for t in texts]
        found: dict[str, list[float]] = {}
        with lock:
            conn = connect()
            try:
                for i in range(0, len(hashes), 500):
                    chunk = hashes[i:i + 500]
                    q = f"SELECT h, vec FROM embeddings WHERE h IN ({','.join('?' * len(chunk))})"
                    found.update({h: _unpack(v) for h, v in conn.execute(q, chunk).fetchall()})
            finally:
                conn.close()
        missing = [(h, t) for h, t in zip(hashes, texts) if h not in found]
        if missing and cached_only:
            if http is _default_http and os.environ.get("PYTEST_CURRENT_TEST"):
                return None  # never a real background network call from a test
            if _bg_fetch.acquire(blocking=False):
                def _bg():
                    try:
                        embed(connect, lock, [t for _, t in missing], task, DOC_TIMEOUT_S, http)
                    finally:
                        _bg_fetch.release()
                threading.Thread(target=_bg, name="jarvis-embed-fill", daemon=True).start()
            return None
        for i in range(0, len(missing), BATCH):
            part = missing[i:i + BATCH]
            vecs = _fetch([t for _, t in part], task, timeout, http)
            if not store:
                found.update({h: v for (h, _), v in zip(part, vecs)})
                continue
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            with lock:
                conn = connect()
                try:
                    conn.executemany("INSERT OR REPLACE INTO embeddings (h, vec, created_at) VALUES (?,?,?)",
                                     [(h, _pack(v), stamp) for (h, _), v in zip(part, vecs)])
                    conn.commit()
                finally:
                    conn.close()
            found.update({h: v for (h, _), v in zip(part, vecs)})
        with _breaker_lock:
            _breaker["fails"] = 0
        return [found[h] for h in hashes]
    except Exception:
        with _breaker_lock:
            _breaker["fails"] += 1
            if _breaker["fails"] >= 3:
                _breaker.update(fails=0, until=time.time() + 300)
        return None


def rank(query_vec: list[float], doc_vecs: list[list[float]]) -> list[tuple[float, int]]:
    """(score, index) of the documents that clear MIN_SCORE and stand MIN_GAP above the median, best first."""
    scores = [cosine(query_vec, v) for v in doc_vecs]
    if not scores:
        return []
    floor = max(MIN_SCORE, median(scores) + MIN_GAP, max(scores) - NEAR_TOP)
    return sorted(((s, i) for i, s in enumerate(scores) if s >= floor), reverse=True)
