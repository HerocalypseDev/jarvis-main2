"""Deepgram Nova-3 STT (Speed Upgrade Phase 1.1).

Uses the plain pre-recorded REST endpoint (POST /v1/listen) via stdlib urllib — no SDK
dependency, same style as jarvis.py's _fish_audio_synthesize. The push-to-talk capture path is
unchanged: the whole hold-to-release buffer is still captured first, then sent here in one shot
(true duplex streaming would need to rewrite audio capture itself, which the task explicitly
says to preserve). Nova-3's pre-recorded latency on a short clip is still a large win over local
Whisper, without touching how audio is captured.

Privacy: when this is used, the raw microphone audio leaves the machine for Deepgram's API.

transcribe() returns the transcript string on success, or None if the call failed or the
confidence landed below the floor — either way jarvis.py's transcribe_pcm() falls back to local
Whisper. It never raises.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.request

import numpy as np

log = logging.getLogger("jarvis")

DEEPGRAM_API_KEY = (os.environ.get("DEEPGRAM_API_KEY") or "").strip()
DEEPGRAM_STT_MODEL = (os.environ.get("JARVIS_DEEPGRAM_STT_MODEL") or "nova-3").strip() or "nova-3"
DEEPGRAM_STT_TIMEOUT_S = float(os.environ.get("JARVIS_DEEPGRAM_STT_TIMEOUT_S") or 8.0)
CONFIDENCE_MIN = float(os.environ.get("JARVIS_DEEPGRAM_STT_MIN_CONFIDENCE") or 0.6)

_LISTEN_URL = "https://api.deepgram.com/v1/listen"


def _urlopen_bounded(req: urllib.request.Request, timeout: float) -> bytes:
    """Hard-timeout watchdog: urlopen's own timeout doesn't reliably fire on a wedged TLS
    connection (same idiom as jarvis.py's _urlopen_hard_timeout, duplicated here so this module
    has no import-time dependency on jarvis.py). Abandons (daemon thread) a call that outlives
    its deadline rather than hanging the mic thread forever."""
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
        raise TimeoutError(f"Deepgram STT request wedged past {timeout}s")
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("data", b"")


def transcribe(mono_f32: np.ndarray, sample_rate: int, timeout_s: float | None = None) -> str | None:
    if not DEEPGRAM_API_KEY:
        return None
    if mono_f32.size == 0:
        return ""
    pcm16 = np.clip(mono_f32 * 32768.0, -32768, 32767).astype(np.int16).tobytes()
    url = (
        f"{_LISTEN_URL}?model={DEEPGRAM_STT_MODEL}&language=en&smart_format=true"
        f"&punctuate=true&encoding=linear16&sample_rate={int(sample_rate)}&channels=1"
    )
    req = urllib.request.Request(
        url,
        data=pcm16,
        method="POST",
        headers={"Authorization": f"Token {DEEPGRAM_API_KEY}", "Content-Type": "audio/raw"},
    )
    try:
        raw = _urlopen_bounded(req, timeout_s or DEEPGRAM_STT_TIMEOUT_S)
        data = json.loads(raw)
        alt = data["results"]["channels"][0]["alternatives"][0]
        transcript = (alt.get("transcript") or "").strip()
        confidence = float(alt.get("confidence") or 0.0)
    except Exception as e:
        log.warning("Deepgram STT request failed: %s", e)
        return None
    if transcript and confidence < CONFIDENCE_MIN:
        log.info(
            "Deepgram STT confidence %.2f below floor %.2f, falling back to Whisper.",
            confidence, CONFIDENCE_MIN,
        )
        return None
    return transcript


def warm() -> None:
    """Connection warm-up (Phase 2.2): a near-silent clip so the TLS handshake happens before
    the first real command instead of during it. Never raises."""
    if not DEEPGRAM_API_KEY:
        return
    try:
        transcribe(np.zeros(1600, dtype=np.float32), 16000, timeout_s=5.0)
    except Exception as e:
        log.debug("Deepgram STT warm-up failed (harmless): %s", e)
