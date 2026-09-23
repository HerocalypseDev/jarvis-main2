"""Follow-up window (QOL pass, 2026-09-23): after Jarvis answers a voice command, keep listening
for a few seconds without push-to-talk, so "...and tomorrow?" just works.

Energy-based voice activity detection over the same mic blocks the push-to-talk loop already
reads: an utterance starts when a block is clearly louder than the room's recent background level,
and ends after a short silence. Pure numpy, no model, no extra audio stream.

ponytail: energy VAD, not a speech model. A loud TV or someone else talking during the window can
start a capture (the transcript then goes through as a command). Swap in a real VAD (e.g. silero)
if that happens too often.
"""

from __future__ import annotations

import os
import time
from collections import deque

import numpy as np


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


WINDOW_S = _env_float("JARVIS_FOLLOWUP_S", 5.0)  # 0 disables the feature
MIN_RMS = _env_float("JARVIS_FOLLOWUP_MIN_RMS", 0.01)  # floor for the speech threshold
NOISE_FACTOR = _env_float("JARVIS_FOLLOWUP_NOISE_FACTOR", 3.0)  # speech = this x background
SILENCE_S = _env_float("JARVIS_FOLLOWUP_SILENCE_S", 0.8)  # pause that ends the utterance
MAX_S = _env_float("JARVIS_FOLLOWUP_MAX_S", 15.0)
MAX_CHAIN = int(_env_float("JARVIS_FOLLOWUP_MAX_CHAIN", 3))  # hands-free turns in a row before the key is needed again
MIN_SPEECH_S = 0.3  # shorter bursts (a click, a cough) are dropped
PREROLL_S = 0.3  # audio kept from just before speech started, so the first syllable isn't clipped


class FollowUpListener:
    def __init__(self, sample_rate: int, window_s: float = WINDOW_S):
        self.sample_rate = sample_rate
        self.window_s = window_s
        self._deadline = 0.0
        self._capture: list[np.ndarray] | None = None
        self._voiced_s = 0.0
        self._silence_s = 0.0
        self._captured_s = 0.0
        self._preroll: deque[np.ndarray] = deque()
        self._preroll_s = 0.0
        self._ambient: deque[float] = deque(maxlen=100)
        self._chain = 0

    def arm(self, now: float | None = None, chained: bool = False) -> None:
        """chained: this reply answered a hands-free follow-up. After MAX_CHAIN of those in a row
        the window stays shut until push-to-talk is used again, so a TV that keeps talking can't
        keep a "conversation" with Jarvis going forever."""
        self._chain = self._chain + 1 if chained else 0
        if self.window_s > 0 and self._chain < MAX_CHAIN:
            self._deadline = (now if now is not None else time.monotonic()) + self.window_s
        else:
            self._deadline = 0.0

    def cancel(self) -> None:
        self._deadline = 0.0
        self._capture = None

    @property
    def capturing(self) -> bool:
        return self._capture is not None

    def _threshold(self) -> float:
        if not self._ambient:
            return MIN_RMS
        return max(MIN_RMS, float(np.median(self._ambient)) * NOISE_FACTOR)

    def feed(self, block: np.ndarray, now: float | None = None) -> np.ndarray | None:
        """Call with every mic block while push-to-talk isn't held and Jarvis isn't talking.
        Returns the captured utterance once it ends, else None."""
        now = now if now is not None else time.monotonic()
        dur = len(block) / self.sample_rate
        rms = float(np.sqrt(np.mean(np.square(block)))) if len(block) else 0.0
        loud = rms > self._threshold()
        if self._capture is None:
            if not loud or now >= self._deadline:
                # Learn the room's background level. Outside the window every block counts, so a
                # TV switched on raises the threshold instead of staying "speech" forever.
                self._ambient.append(rms)
            self._preroll.append(block.copy())
            self._preroll_s += dur
            while self._preroll_s > PREROLL_S and len(self._preroll) > 1:
                self._preroll_s -= len(self._preroll.popleft()) / self.sample_rate
            if loud and now < self._deadline:
                self._capture = list(self._preroll)
                self._captured_s = self._preroll_s
                self._voiced_s, self._silence_s = dur, 0.0
                self._preroll.clear()
                self._preroll_s = 0.0
            return None
        self._capture.append(block.copy())
        self._captured_s += dur
        if loud:
            self._voiced_s += dur
            self._silence_s = 0.0
        else:
            self._silence_s += dur
        if self._silence_s < SILENCE_S and self._captured_s < MAX_S:
            return None
        audio, voiced = np.concatenate(self._capture, axis=0), self._voiced_s
        self._capture = None
        if voiced < MIN_SPEECH_S:
            return None  # a click or cough: keep whatever is left of the window
        self._deadline = 0.0  # one follow-up per window; the next reply re-arms it
        return audio
