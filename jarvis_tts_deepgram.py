"""Deepgram Aura 2 TTS (Speed Upgrade Phase 1.2; WebSocket streaming added in the cloud-latency
pass, Phase B).

Two paths:
- synthesize(): POST /v1/speak via stdlib urllib (no SDK dependency), requesting linear16/WAV
  output directly so the response is self-describing through stdlib `wave` — the exact same
  (pcm_int16_bytes, sample_rate) contract jarvis.py's _fish_audio_synthesize/_piper_synthesize
  already use, so speak_text() can swap engines without changing how audio is played or cached.
  Raises on any failure (missing key, network error, bad response) — the caller decides whether
  to fall back.
- StreamingSynthesis: wss://api.deepgram.com/v1/speak, Deepgram's dedicated streaming TTS
  endpoint (distinct from the streaming *STT* endpoint) — sends the text once, then yields raw
  PCM audio chunks as Aura 2 generates them (no WAV wrapper on a WS stream; the sample rate is
  whatever was requested, DEEPGRAM_TTS_SAMPLE_RATE by default), so jarvis.py can start playing
  before the whole utterance has been synthesized. Needs the `websocket-client` package (see
  jarvis_stt_deepgram.py's docstring — same dependency, already required for streaming STT).

Privacy: when either path is used, the text being spoken leaves the machine for Deepgram's API
(same category of exposure as Fish Audio already documented in CLAUDE.md).
"""

from __future__ import annotations

import io
import json
import logging
import os
import threading
import urllib.request
import wave

try:
    import websocket as _websocket_lib  # websocket-client package (import name: websocket)
except ImportError:  # pragma: no cover - exercised only if the dependency is missing
    _websocket_lib = None

log = logging.getLogger("jarvis")

DEEPGRAM_API_KEY = (os.environ.get("DEEPGRAM_API_KEY") or "").strip()
DEEPGRAM_TTS_MODEL = (
    os.environ.get("JARVIS_DEEPGRAM_TTS_MODEL") or "aura-2-thalia-en"
).strip() or "aura-2-thalia-en"
DEEPGRAM_TTS_TIMEOUT_S = float(os.environ.get("JARVIS_DEEPGRAM_TTS_TIMEOUT_S") or 15.0)
DEEPGRAM_TTS_SAMPLE_RATE = 24000
STREAM_ENABLED = (os.environ.get("JARVIS_DEEPGRAM_TTS_STREAM") or "1").strip().lower() not in (
    "0", "false", "no", "off",
)
STREAM_CONNECT_TIMEOUT_S = float(os.environ.get("JARVIS_DEEPGRAM_TTS_STREAM_TIMEOUT_S") or 15.0)

_SPEAK_URL = "https://api.deepgram.com/v1/speak"
_SPEAK_WS_URL = "wss://api.deepgram.com/v1/speak"


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


class StreamingSynthesis:
    """One request to Deepgram's streaming speak WebSocket. Usage:
        session = StreamingSynthesis(text)
        if session.connect():          # False -> caller falls back to synthesize() (REST)
            for chunk in session.chunks():   # raw int16 PCM bytes, as they're generated
                ...play chunk...
            session.close()
    chunks() raises if the connection drops mid-stream (after possibly already yielding some
    real chunks) — the caller must decide whether any audio had already played before treating
    that as safe to retry with a different engine (see jarvis.py's _play_pcm_stream/
    _speak_streamed: once real audio has started, falling back would double-speak, so a
    mid-stream failure is accepted as a truncated sentence, not silently replayed elsewhere).
    """

    def __init__(self, text: str, sample_rate: int = DEEPGRAM_TTS_SAMPLE_RATE, timeout_s: float | None = None):
        self.text = text
        self.sample_rate = sample_rate
        self.timeout_s = timeout_s or STREAM_CONNECT_TIMEOUT_S
        self._ws = None

    def connect(self) -> bool:
        if not DEEPGRAM_API_KEY or _websocket_lib is None:
            return False
        url = f"{_SPEAK_WS_URL}?model={DEEPGRAM_TTS_MODEL}&encoding=linear16&sample_rate={self.sample_rate}"
        try:
            self._ws = _websocket_lib.create_connection(
                url,
                header=[f"Authorization: Token {DEEPGRAM_API_KEY}"],
                timeout=self.timeout_s,
            )
            self._ws.send(json.dumps({"type": "Speak", "text": self.text}))
            # "Close": flush the buffer and close the connection gracefully after all audio for
            # the text already sent has been generated — no separate Flush needed for one text.
            self._ws.send(json.dumps({"type": "Close"}))
        except Exception as e:
            log.warning("Deepgram streaming TTS connect/send failed, using REST instead: %s", e)
            self._ws = None
            return False
        return True

    def chunks(self):
        """Generator yielding raw int16 PCM bytes as Aura 2 generates them. Text control/warning
        frames (JSON, e.g. {"type": "Warning", ...}) are silently ignored — only binary frames
        are audio."""
        if self._ws is None:
            return
        while True:
            msg = self._ws.recv()
            if not msg:
                return
            if isinstance(msg, (bytes, bytearray)):
                yield bytes(msg)
            # else: a text/JSON control frame — nothing actionable for playback, skip it.

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
