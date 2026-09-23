"""Deepgram Nova-3 STT (Speed Upgrade Phase 1.1, streaming added in the cloud-latency pass).

Two paths, same confidence gate and same (text | None) contract either way — None always means
"fall back", never raises out to the caller:

- transcribe(): the pre-recorded REST endpoint (POST /v1/listen) via stdlib urllib — no SDK
  dependency, same style as jarvis.py's _fish_audio_synthesize. Used for a full already-captured
  buffer (the REST/Whisper fallback path when streaming isn't used or didn't produce a result).
- StreamingSession: the live WebSocket endpoint (wss://.../v1/listen), fed PCM chunks *while*
  push-to-talk is held so transcription mostly finishes by the time the key is released, instead
  of starting only then. Needs the `websocket-client` package (a small, widely-used sync client —
  see SPEED.md for why this one dependency was added). Falls back to returning None (caller uses
  REST on the full buffer, then Whisper) on any connect/send/protocol failure — the push-to-talk
  capture loop itself never touches the network directly; feed() only queues bytes for a
  dedicated sender thread, so a slow/stalled connection can never stall audio capture.

Privacy: when either path is used, the raw microphone audio leaves the machine for Deepgram's API.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import urllib.request

import numpy as np

try:
    import websocket as _websocket_lib  # websocket-client package (import name: websocket)
except ImportError:  # pragma: no cover - exercised only if the dependency is missing
    _websocket_lib = None

log = logging.getLogger("jarvis")

DEEPGRAM_API_KEY = (os.environ.get("DEEPGRAM_API_KEY") or "").strip()
DEEPGRAM_STT_MODEL = (os.environ.get("JARVIS_DEEPGRAM_STT_MODEL") or "nova-3").strip() or "nova-3"
# "en" (default), another language code, or "multi" (Nova-3's code-switching mode for mixed speech).
DEEPGRAM_LANGUAGE = (os.environ.get("JARVIS_DEEPGRAM_LANGUAGE") or "en").strip() or "en"
DEEPGRAM_STT_TIMEOUT_S = float(os.environ.get("JARVIS_DEEPGRAM_STT_TIMEOUT_S") or 8.0)
CONFIDENCE_MIN = float(os.environ.get("JARVIS_DEEPGRAM_STT_MIN_CONFIDENCE") or 0.6)

_LISTEN_URL = "https://api.deepgram.com/v1/listen"
_LISTEN_WS_URL = "wss://api.deepgram.com/v1/listen"
STREAM_ENABLED = (os.environ.get("JARVIS_DEEPGRAM_STT_STREAM") or "1").strip().lower() not in (
    "0", "false", "no", "off",
)
STREAM_SOCKET_TIMEOUT_S = float(os.environ.get("JARVIS_DEEPGRAM_STREAM_TIMEOUT_S") or 15.0)
STREAM_FINALIZE_TIMEOUT_S = float(os.environ.get("JARVIS_DEEPGRAM_STREAM_FINALIZE_TIMEOUT_S") or 5.0)


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
        f"{_LISTEN_URL}?model={DEEPGRAM_STT_MODEL}&language={DEEPGRAM_LANGUAGE}&smart_format=true"
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


class StreamingSession:
    """One push-to-talk hold's live Deepgram Nova-3 WebSocket session.

    Usage (see jarvis.py's push-to-talk loop):
        session = StreamingSession(sample_rate)
        if session.start():          # False -> connect failed, caller skips straight to REST
            while ptt_held:
                session.feed(block)  # block: float32 numpy array, same shape capture produces
            result = session.finish()  # (transcript, confidence) or None on any failure

    feed() only enqueues bytes (no network I/O on the caller's thread — a dedicated sender
    thread drains the queue and calls the blocking WebSocket send), so a slow or stalled
    connection can never stall the audio capture loop that's calling feed() every ~40ms.
    A second background thread reads incoming Results/Metadata messages and keeps the latest
    finalized transcript. Nothing here raises outward — every failure just makes finish() return
    None so the caller falls back to REST-on-the-full-buffer, then Whisper, same as before.
    """

    def __init__(self, sample_rate: int):
        self.sample_rate = int(sample_rate)
        self._ws = None
        self._send_q: queue.Queue = queue.Queue()
        self._sender_thread: threading.Thread | None = None
        self._receiver_thread: threading.Thread | None = None
        self._transcript = ""
        self._confidence = 0.0
        self._closed = threading.Event()  # set when the receiver loop has ended (any reason)
        self._send_failed = threading.Event()
        self._start_done = threading.Event()  # set once start() has resolved, success or not
        self._lock = threading.Lock()

    def start(self) -> bool:
        if not DEEPGRAM_API_KEY or _websocket_lib is None:
            self._start_done.set()
            return False
        url = (
            f"{_LISTEN_WS_URL}?model={DEEPGRAM_STT_MODEL}&language={DEEPGRAM_LANGUAGE}&smart_format=true"
            f"&punctuate=true&encoding=linear16&sample_rate={self.sample_rate}&channels=1"
            f"&interim_results=true&endpointing=300"
        )
        try:
            self._ws = _websocket_lib.create_connection(
                url,
                header=[f"Authorization: Token {DEEPGRAM_API_KEY}"],
                timeout=STREAM_SOCKET_TIMEOUT_S,
            )
        except Exception as e:
            log.warning("Deepgram streaming STT connect failed, using REST instead: %s", e)
            self._start_done.set()
            return False
        self._sender_thread = threading.Thread(target=self._send_loop, daemon=True)
        self._receiver_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._sender_thread.start()
        self._receiver_thread.start()
        self._start_done.set()
        return True

    def feed(self, block_f32: np.ndarray) -> None:
        # Enqueues unconditionally, even before start() has finished connecting (jarvis.py kicks
        # start() off on its own thread right at PTT-press so the capture loop is never blocked
        # on the connect) — the queue just holds the bytes until _send_loop exists to drain them,
        # so nothing said in the first moment of a hold is ever dropped while the socket is still
        # coming up. If start() ultimately fails, these bytes are simply never read by anyone and
        # are dropped with the session object, same as if feed() had never been called.
        if self._send_failed.is_set() or block_f32.size == 0:
            return
        mono = np.mean(block_f32.astype(np.float64), axis=1) if block_f32.ndim > 1 else block_f32
        pcm16 = np.clip(mono.astype(np.float32) * 32768.0, -32768, 32767).astype(np.int16).tobytes()
        self._send_q.put(pcm16)

    def _send_loop(self) -> None:
        # Control messages (Finalize/CloseStream, sent as str) go through this same queue as the
        # audio chunks (bytes) rather than being sent directly from finish()'s caller thread —
        # otherwise they could race ahead of trailing audio still waiting in the queue and reach
        # Deepgram before the last few chunks, truncating the transcript.
        while True:
            item = self._send_q.get()
            if item is None:  # sentinel: stop
                return
            try:
                if isinstance(item, bytes):
                    self._ws.send_binary(item)
                else:
                    self._ws.send(item)
            except Exception as e:
                log.warning("Deepgram streaming STT send failed: %s", e)
                self._send_failed.set()
                return

    def _recv_loop(self) -> None:
        try:
            while True:
                msg = self._ws.recv()
                if not msg:
                    return
                try:
                    data = json.loads(msg)
                except (TypeError, ValueError):
                    continue
                if data.get("type") != "Results":
                    continue
                alternatives = (data.get("channel") or {}).get("alternatives") or [{}]
                transcript = (alternatives[0].get("transcript") or "").strip()
                if not transcript or not data.get("is_final"):
                    continue
                with self._lock:
                    self._transcript = f"{self._transcript} {transcript}".strip()
                    self._confidence = float(alternatives[0].get("confidence") or 0.0)
        except Exception as e:
            log.debug("Deepgram streaming STT receive loop ended: %s", e)
        finally:
            self._closed.set()

    def finish(self, timeout_s: float | None = None) -> tuple[str, float] | None:
        """Flushes and closes the session, returning (transcript, confidence) or None on any
        failure (send never got through, connect never succeeded, or nothing usable came back).
        Always tears the connection down, even when returning None."""
        # A very short hold can release before start() (running on its own thread since it does
        # a blocking connect) has resolved — wait for it rather than racing ahead and wrongly
        # concluding "no session" while a connection is still in flight. Bounded by start()'s own
        # connect timeout, so this can never hang past that.
        if not self._start_done.wait(STREAM_SOCKET_TIMEOUT_S + 2):
            log.warning("Deepgram streaming STT: start() didn't resolve in time, using REST instead.")
            return None
        if self._ws is None:
            return None
        # Enqueued (not sent directly) so any audio chunks still waiting in the queue are always
        # flushed to Deepgram before Finalize/CloseStream — see the note in _send_loop.
        self._send_q.put(json.dumps({"type": "Finalize"}))
        self._send_q.put(json.dumps({"type": "CloseStream"}))
        self._send_q.put(None)  # stop the sender loop once the above are sent
        bound = timeout_s or STREAM_FINALIZE_TIMEOUT_S
        # Wait for the *sender* to actually finish draining the queue (and thus learn about a
        # send failure) before waiting for the receiver — the two threads are otherwise fully
        # decoupled, so a fast-closing receiver (server hangs up right away) could otherwise let
        # this fall through to reading a transcript before the sender ever got a chance to run.
        if self._sender_thread is not None:
            self._sender_thread.join(bound)
        self._closed.wait(bound)
        try:
            self._ws.close()
        except Exception:
            pass
        if self._send_failed.is_set():
            return None
        with self._lock:
            transcript, confidence = self._transcript, self._confidence
        if transcript and confidence < CONFIDENCE_MIN:
            log.info(
                "Deepgram streaming STT confidence %.2f below floor %.2f, falling back.",
                confidence, CONFIDENCE_MIN,
            )
            return None
        return transcript, confidence
