"""Basic voice tone/sentiment awareness for Jarvis.

Rule-based, deliberately simple: keyword/pattern cues over the transcribed text decide
the tone category, optionally amplified by two cheap prosodic signals (loudness, speaking
pace) when the raw audio is available. This is not a full sentiment model — no new
dependency, no ML — just enough signal to let responses adapt (terser when the user
sounds frustrated, more explanatory when curious, faster/more direct when urgent) rather
than treating every utterance identically.

Self-contained: pure functions, no state, no import-time dependency back on jarvis.py.
jarvis.py calls analyze_tone() once per command and folds tone_context_line() into the
system prompt for that turn.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger("jarvis.voice_tone")

try:
    import numpy as np
except ImportError:  # prosodic analysis just degrades to text-only if numpy is missing
    np = None

# (category, weight, compiled pattern) — weight lets a strong single cue (e.g. "i give up")
# count for more than a milder one (e.g. "again") without a full ML model.
_CUE_PATTERNS: dict[str, list[tuple[float, "re.Pattern[str]"]]] = {
    "frustrated": [
        (2.0, re.compile(r"\b(ugh+|i give up|sick of|fed up)\b", re.I)),
        (1.5, re.compile(r"\b(seriously|come on|still (broken|not working|doesn'?t work))\b", re.I)),
        (1.0, re.compile(r"\b(annoying|frustrat\w*|not working|broken again|why (won'?t|isn'?t|doesn'?t))\b", re.I)),
        (0.75, re.compile(r"!!+")),
    ],
    "urgent": [
        (2.0, re.compile(r"\b(asap|asap!|right now|immediately|emergency)\b", re.I)),
        (1.5, re.compile(r"\b(urgent(ly)?|hurry|as soon as possible|need(s)? this now)\b", re.I)),
        (1.0, re.compile(r"\b(quick(ly)?|now please|before .* (starts|leaves|closes))\b", re.I)),
    ],
    "curious": [
        (1.5, re.compile(r"\b(i'?m curious|i wonder|wondering)\b", re.I)),
        (1.0, re.compile(r"\b(how (does|do|is|are|can)|why (does|do|is|are)|what if|what happens (if|when))\b", re.I)),
        (0.5, re.compile(r"\?")),
    ],
    "positive": [
        (1.5, re.compile(r"\b(thank(s| you)|appreciate it|awesome|love (it|this))\b", re.I)),
        (1.0, re.compile(r"\b(great job|perfect|nice one|well done)\b", re.I)),
    ],
    "sad": [
        (1.5, re.compile(r"\b(exhausted|overwhelmed|stressed( out)?|so tired)\b", re.I)),
        (1.0, re.compile(r"\b(sad|disappointed|sorry to (bother|ask)|rough day)\b", re.I)),
    ],
}

# Priority when multiple categories tie on score — actionable states first.
_TONE_PRIORITY = ("frustrated", "urgent", "sad", "curious", "positive", "neutral")

LOUD_RMS_THRESHOLD = 0.08
FAST_WPS_THRESHOLD = 3.5
SLOW_WPS_THRESHOLD = 1.0
MIN_CONFIDENCE_TO_REPORT = 0.35


def _lexical_scores(transcript: str) -> dict[str, tuple[float, list[str]]]:
    scores: dict[str, tuple[float, list[str]]] = {}
    for category, patterns in _CUE_PATTERNS.items():
        total = 0.0
        hits: list[str] = []
        for weight, pattern in patterns:
            matches = pattern.findall(transcript)
            if matches:
                total += weight * len(matches)
                hits.append(pattern.pattern)
        if total:
            scores[category] = (total, hits)
    return scores


def _prosody(transcript: str, audio, sample_rate: int | None) -> dict:
    if np is None or audio is None or not sample_rate or getattr(audio, "size", 0) == 0:
        return {}
    duration_s = audio.size / float(sample_rate)
    if duration_s <= 0:
        return {}
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    word_count = len(transcript.split())
    words_per_second = word_count / duration_s if duration_s > 0 else 0.0
    return {
        "rms": rms,
        "loud": rms >= LOUD_RMS_THRESHOLD,
        "words_per_second": words_per_second,
        "fast": words_per_second >= FAST_WPS_THRESHOLD,
        "slow": 0 < words_per_second <= SLOW_WPS_THRESHOLD,
    }


def analyze_tone(transcript: str, audio=None, sample_rate: int | None = None) -> dict:
    """Returns {"tone": category, "confidence": 0..1, "signals": [short strings]}.
    category is one of _TONE_PRIORITY. Text-only when audio/sample_rate are omitted
    (typed/phone commands); adds loudness/pace amplification when given (voice commands)."""
    transcript = transcript or ""
    lexical = _lexical_scores(transcript)
    prosody = _prosody(transcript, audio, sample_rate)

    if not lexical:
        # No keyword cues — prosody alone can still surface urgency (fast, clipped speech).
        if prosody.get("fast") and len(transcript.split()) <= 12:
            return {"tone": "urgent", "confidence": 0.4, "signals": ["fast speaking pace"]}
        return {"tone": "neutral", "confidence": 1.0, "signals": []}

    best_category = max(
        lexical,
        key=lambda c: (lexical[c][0], -_TONE_PRIORITY.index(c)),
    )
    score, hits = lexical[best_category]
    confidence = min(1.0, 0.3 + 0.15 * score)
    signals = [f"{len(hits)} text cue(s)"] if hits else []

    if prosody.get("loud") and best_category in ("frustrated", "urgent"):
        confidence = min(1.0, confidence + 0.2)
        signals.append("raised voice")
    if prosody.get("fast") and best_category in ("urgent", "frustrated"):
        confidence = min(1.0, confidence + 0.15)
        signals.append("fast speaking pace")
    if prosody.get("slow") and best_category in ("sad",):
        confidence = min(1.0, confidence + 0.15)
        signals.append("slow speaking pace")

    return {"tone": best_category, "confidence": round(confidence, 2), "signals": signals}


_TONE_GUIDANCE = {
    "frustrated": "be concise, solution-focused, and skip unnecessary preamble",
    "urgent": "prioritize speed — lead with the answer/action, minimize small talk",
    "curious": "feel free to explain a bit more than usual, they're engaged",
    "sad": "be warm and brief, don't pile on extra asks",
    "positive": "keep the energy — a short acknowledgment is fine before moving on",
}


def tone_context_line(result: dict) -> str:
    """Short line to fold into the agent system prompt for this turn; empty string if the
    tone isn't confident enough to be worth mentioning (avoids noise on ambiguous input)."""
    if not result:
        return ""
    tone = result.get("tone", "neutral")
    confidence = result.get("confidence", 0.0)
    if tone == "neutral" or confidence < MIN_CONFIDENCE_TO_REPORT:
        return ""
    guidance = _TONE_GUIDANCE.get(tone, "")
    return f"\n\nVoice tone detected: {tone} (confidence {confidence:.0%}). {guidance}.".rstrip()
