"""Deepgram Aura 2 TTS (Speed Upgrade Phase 1.2).

POST /v1/speak via stdlib urllib (no SDK dependency), requesting linear16/WAV output directly so
the response is self-describing through stdlib `wave` — the exact same (pcm_int16_bytes,
sample_rate) contract jarvis.py's _fish_audio_synthesize/_piper_synthesize already use, so
speak_text() can swap engines without changing how the audio is played or cached.

Privacy: when this is used, the text being spoken leaves the machine for Deepgram's API (same
category of exposure as Fish Audio already documented in CLAUDE.md).

synthesize() raises on any failure (missing key, network error, bad response) — same contract as
the Fish/Piper functions; the caller decides whether to fall back.
"""

from __future__ import annotations

import io
import json
import logging
import os
import threading
import urllib.request
import wave

log = logging.getLogger("jarvis")

DEEPGRAM_API_KEY = (os.environ.get("DEEPGRAM_API_KEY") or "").strip()
DEEPGRAM_TTS_MODEL = (
    os.environ.get("JARVIS_DEEPGRAM_TTS_MODEL") or "aura-2-thalia-en"
).strip() or "aura-2-thalia-en"
DEEPGRAM_TTS_TIMEOUT_S = float(os.environ.get("JARVIS_DEEPGRAM_TTS_TIMEOUT_S") or 15.0)
DEEPGRAM_TTS_SAMPLE_RATE = 24000

_SPEAK_URL = "https://api.deepgram.com/v1/speak"


def _urlopen_bounded(req: urllib.request.Request, timeout: float) -> bytes:
    """Same hard-timeout watchdog idiom as jarvis_stt_deepgram._urlopen_bounded — duplicated
    rather than shared so these two backend modules stay independently swappable/importable."""
    outcome: dict = {}

    def _do() -> None:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                outcome["data"] = resp.read()
        except Exception as e:
            outcome["error"] = e

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout + 3)
    if t.is_alive():
        raise TimeoutError(f"Deepgram TTS request wedged past {timeout}s")
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("data", b"")


def synthesize(text: str, timeout_s: float | None = None) -> tuple[bytes, int]:
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY is not set")
    url = (
        f"{_SPEAK_URL}?model={DEEPGRAM_TTS_MODEL}&encoding=linear16"
        f"&sample_rate={DEEPGRAM_TTS_SAMPLE_RATE}&container=wav"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps({"text": text}).encode(),
        method="POST",
        headers={"Authorization": f"Token {DEEPGRAM_API_KEY}", "Content-Type": "application/json"},
    )
    raw_wav = _urlopen_bounded(req, timeout_s or DEEPGRAM_TTS_TIMEOUT_S)
    with wave.open(io.BytesIO(raw_wav), "rb") as wf:
        sample_rate = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    return pcm, sample_rate


def warm() -> None:
    """Connection warm-up (Phase 2.2): a tiny synth-and-discard so the first real reply isn't
    the one paying for TLS/DNS. Never raises."""
    if not DEEPGRAM_API_KEY:
        return
    try:
        synthesize(".", timeout_s=5.0)
    except Exception as e:
        log.debug("Deepgram TTS warm-up failed (harmless): %s", e)
