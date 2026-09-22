"""Per-voice-command latency tracker (Speed Upgrade Phase 0).

One VoiceLatency lives on a thread-local for the duration of a push-to-talk command: t0 is set
on creation (capture end), then jarvis.py marks "stt" (transcript ready), "ttft" (first Claude
response of the agent loop) and "tts_ttfa" (first audio chunk ready to play) as it goes. finish()
logs one grep-able line and keeps the last MAX_HISTORY in memory (recent(), for the dashboard or
ad-hoc inspection — nothing here persists to disk).

Text/dashboard/phone commands never create one of these (current() is None for them), so every
call site in jarvis.py that reads it must handle None.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque

log = logging.getLogger("jarvis")

MAX_HISTORY = 200
_history: deque[dict] = deque(maxlen=MAX_HISTORY)
_history_lock = threading.Lock()
_ctx = threading.local()


class VoiceLatency:
    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.stt_backend = ""
        self.tts_backend = ""
        self.intent = ""
        self.path = ""  # "deterministic" | "reduced_tools" | "full" — set by jarvis.py's intent router
        self._marks: dict[str, float] = {}

    def mark(self, stage: str) -> None:
        self._marks.setdefault(stage, time.monotonic())

    def _ms(self, stage: str) -> int | None:
        t = self._marks.get(stage)
        return int((t - self.t0) * 1000) if t is not None else None

    def finish(self) -> None:
        stt_ms, ttft_ms, tts_ms = self._ms("stt"), self._ms("ttft"), self._ms("tts_ttfa")
        e2e_ms = int((time.monotonic() - self.t0) * 1000)
        log.info(
            "latency stt=%sms ttft=%sms tts=%sms e2e=%sms stt_backend=%s tts_backend=%s intent=%s path=%s",
            stt_ms, ttft_ms, tts_ms, e2e_ms, self.stt_backend or "-", self.tts_backend or "-",
            self.intent or "-", self.path or "-",
        )
        with _history_lock:
            _history.append({
                "stt_ms": stt_ms, "ttft_ms": ttft_ms, "tts_ttfa_ms": tts_ms, "e2e_ms": e2e_ms,
                "stt_backend": self.stt_backend, "tts_backend": self.tts_backend,
                "intent": self.intent, "path": self.path, "at": time.time(),
            })


def start() -> VoiceLatency:
    lat = VoiceLatency()
    _ctx.current = lat
    return lat


def current() -> VoiceLatency | None:
    return getattr(_ctx, "current", None)


def end() -> None:
    lat = current()
    if lat is not None:
        lat.finish()
    _ctx.current = None


def recent(n: int = 20) -> list[dict]:
    with _history_lock:
        return list(_history)[-n:]


# --- cheap deterministic intent classifier (Phase 2.3 — logged only; jarvis.py's default model
# is already Haiku, so there is no cheaper model left to route simple intents to. Logging the
# intent still gives real signal for future routing/metrics decisions.) -----------------------
_INTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("time", re.compile(r"\bwhat(?:'s| is)?\s+(?:the\s+)?time\b|\bcurrent time\b", re.I)),
    ("date", re.compile(r"\bwhat(?:'s| is)?\s+(?:the\s+)?date\b|\bwhat day is it\b", re.I)),
    ("volume", re.compile(r"\bvolume\b|\b(?:mute|unmute)\b|\bturn (?:it |the sound )?(?:up|down)\b", re.I)),
    ("open_app", re.compile(r"^\s*open\s+\S", re.I)),
    ("timer_reminder", re.compile(r"\b(?:set|start)\s+a?\s*(?:timer|reminder|alarm)\b", re.I)),
]


def classify_intent(transcript: str) -> str:
    t = (transcript or "").strip()
    for name, pattern in _INTENT_PATTERNS:
        if pattern.search(t):
            return name
    return "complex"
