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
# "greeting"/"thanks" are whole-transcript matches (\A...\Z, not a bare \b search) on purpose:
# "hi" alone is trivial social noise, but "hi, what's the weather" is a real command that only
# happens to start with "hi" and must fall through to "complex" like anything else — see
# jarvis.py's _deterministic_intent_reply, which answers these two with no LLM call at all
# (voice-bug follow-up, 2026-09-22: this also means the filler-phrase timer for these transcripts
# never starts in the first place, since jarvis.py only spawns it once a Claude call is needed).
_INTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("greeting", re.compile(r"\A\s*(?:hi|hey|hello|hiya|yo)\s*(?:,?\s*jarvis)?\s*[.!]?\s*\Z", re.I)),
    ("thanks", re.compile(r"\A\s*(?:thanks|thank you|thx|ty)\s*(?:,?\s*jarvis)?\s*[.!]?\s*\Z", re.I)),
    # Briefing v2 (2026-09-23): composed from local data by jarvis_briefing, no LLM call.
    ("briefing", re.compile(r"\A\s*(?:jarvis,?\s*)?(?:good morning|(?:give me |what'?s )?(?:my |the )?(?:morning )?briefing|brief me)"
                            r"(?:,?\s*jarvis)?\W*\Z", re.I)),
    ("urgent", re.compile(r"\A\s*(?:jarvis,?\s*)?(?:what(?:'s| is) urgent|anything urgent|what needs me|what needs my attention"
                          r"|what do i need to (?:know|do)(?: today| now)?)(?:,?\s*jarvis)?\W*\Z", re.I)),
    # Second wave (2026-09-23): "stop talking" says nothing back; a standing reply-length choice.
    ("hush", re.compile(r"\A\s*(?:jarvis,?\s*)?(?:stop talking|stop|shut up|be quiet|quiet|hush|enough|silence|that's enough)"
                        r"(?:,?\s*(?:please|jarvis))?\W*\Z", re.I)),
    ("reply_style", re.compile(r"\A\s*(?:jarvis,?\s*)?(?:please\s+)?(?:(?:be|keep (?:it|answers|replies|them))\s+(?:brief|short|concise|terse)"
                               r"|(?:give me |use )?(?:shorter|brief|short|concise|longer|detailed|more detailed|normal|regular|default) (?:answers|replies)"
                               r"|be more (?:detailed|thorough)|go back to normal (?:answers|replies|length))"
                               r"(?:\s+from now on)?(?:,?\s*please)?\W*\Z", re.I)),
    ("safe_mode", re.compile(r"\A\s*(?:jarvis,?\s*)?(?:(?:turn|switch|put)\s+(?:on|off|me in|into)?\s*safe mode(?:\s+(?:on|off))?"
                             r"|(?:enable|disable|start|stop|exit|leave|enter)\s+safe mode|safe mode(?:\s+(?:on|off|status))?"
                             r"|is safe mode on)\W*\Z", re.I)),
    # QOL pass (2026-09-23): handled in jarvis.py without (or with a rewritten) LLM call.
    # Anchored (audit 2026-09-23): "run diagnostics on my network" or "are you working on the
    # report?" are real requests, not a self-check.
    ("self_check", re.compile(r"\bself[- ]?check\b|\bcheck yourself\b"
                              r"|\A\s*(?:jarvis,?\s*)?(?:(?:run|do)\s+(?:a\s+)?)?(?:diagnostics?|health ?check)(?: on yourself)?\W*\Z"
                              r"|\A\s*(?:jarvis,?\s*)?are you (?:ok|okay|alright|working)(?:,?\s*jarvis)?\W*\Z", re.I)),
    ("repeat", re.compile(r"\A\s*(?:jarvis,?\s*)?(?:repeat that|say that again|what did you say|come again|repeat)\W*\Z", re.I)),
    ("shorter", re.compile(r"\A\s*(?:jarvis,?\s*)?(?:say that shorter|shorter|tl;?dr|summari[sz]e that|give me the short version|shorter please)\W*\Z", re.I)),
    ("last_actions", re.compile(r"\A\s*(?:jarvis,?\s*)?what (?:did|have) you (?:just )?(?:do|done)"
                                r"(?: just now| recently| lately| last| so far| today)?\W*\Z"
                                r"|\bwhat was the last thing you did\b", re.I)),
    ("undo", re.compile(r"\A\s*(?:jarvis,?\s*)?undo(?: that| it| the last (?:thing|action)| what you (?:just )?did)?\W*\Z", re.I)),
    # Short (<= 12 words) and not a coding question: "how do I write a python timer that stops
    # after 5 seconds" must reach the agent loop, not set or cancel a real timer.
    ("timer", re.compile(r"\A(?=(?:\S+\s+){0,11}\S+\s*\Z)(?!.*\b(?:how (?:do|to|does|can|would)|code|python|"
                         r"script|function|program|write|explain)\b).*\b(?:timers?|stopwatch)\b", re.I)),
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
