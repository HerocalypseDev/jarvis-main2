"""Optional "Hey Jarvis" wake word (opt-in, off by default: Settings -> JARVIS_WAKE_WORD).

Runs the open-source openWakeWord model (bundled `hey_jarvis` ONNX, on the CPU, local, no account, no
network) over the mic blocks the push-to-talk loop already reads. When it hears the phrase, the main
loop hands the last second or so of audio to the follow-up listener, which keeps capturing until the
speaker stops; the transcript then goes through the normal command pipeline.

What it is NOT: a way to confirm anything. A wake-word capture is a hands-free capture, so the
catastrophic confirmation gate refuses a spoken "yes" from it exactly as it does for the follow-up
window (a TV saying "Hey Jarvis, yes" must never approve a shutdown).

Cost (measured on a 60 s clip): ~+140 MB RAM, ~7% of one CPU core while listening. Nothing is
recorded or sent anywhere until the phrase is heard; only then does the captured command go to the
speech-to-text engine like any other voice command. Everything here degrades to "off" if the
optional `openwakeword` package or its model is missing.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import deque

import numpy as np

log = logging.getLogger("jarvis")

MODEL_RATE = 16000
FRAME = 1280  # samples of 16 kHz audio per prediction (80 ms), what openWakeWord expects
DEFAULT_THRESHOLD = 0.5
COOLDOWN_S = 2.5  # after a hit, ignore further hits (the same phrase scores high for a few frames)
RECENT_S = 1.6  # audio kept so the capture can start at "hey", not after it


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


def enabled() -> bool:
    return (os.environ.get("JARVIS_WAKE_WORD") or "").strip().lower() in ("1", "true", "yes", "on")


def threshold() -> float:
    return min(0.99, max(0.05, _env_float("JARVIS_WAKE_THRESHOLD", DEFAULT_THRESHOLD)))


def _default_model_factory():
    """Loads the bundled hey_jarvis model. Raises ImportError/FileNotFoundError when unavailable."""
    import openwakeword  # optional dependency
    from openwakeword.model import Model

    path = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models", "hey_jarvis_v0.1.onnx")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    try:  # 0.4.x: ONNX only, models by path
        return Model(wakeword_model_paths=[path])
    except TypeError:  # newer releases: renamed argument, explicit runtime
        return Model(wakeword_models=[path], inference_framework="onnx")


def resample_block(chunk: np.ndarray, sample_rate: int, n_out: int = FRAME) -> np.ndarray:
    """One chunk of mono float audio at `sample_rate` -> `n_out` int16 samples at 16 kHz (linear
    interpolation after a light 3-tap smoothing when downsampling, enough for a wake-word model)."""
    x = np.asarray(chunk, dtype=np.float32)
    if sample_rate > MODEL_RATE * 1.2 and len(x) >= 3:
        x = np.convolve(x, np.array([0.25, 0.5, 0.25], dtype=np.float32), mode="same")
    src = np.linspace(0.0, len(x) - 1, num=n_out)
    y = np.interp(src, np.arange(len(x)), x)
    return (np.clip(y, -1.0, 1.0) * 32767.0).astype(np.int16)


class WakeListener:
    """feed() every mic block (mono float32) while nothing else is using the mic; True = phrase heard."""

    def __init__(self, sample_rate: int, model_factory=None, thr: float | None = None, cooldown_s: float = COOLDOWN_S,
                 async_load: bool = False):
        """async_load: load the model on a background thread and ignore blocks until it is ready, so the
        audio loop (which must keep reading the mic) never blocks on the ~1 s model load."""
        self.sample_rate = sample_rate
        self._async = async_load
        self._loading = False
        self._factory = model_factory or _default_model_factory
        self._thr = thr
        self.cooldown_s = cooldown_s
        self._model = None
        self._failed = False
        self._pending: list[np.ndarray] = []
        self._pending_n = 0
        self._native_frame = max(1, int(round(FRAME * sample_rate / MODEL_RATE)))
        self._recent: deque[np.ndarray] = deque()
        self._recent_s = 0.0
        self._quiet_until = 0.0
        self.last_score = 0.0

    @property
    def available(self) -> bool:
        """False once loading the model has failed (missing package/model): the feature then stays off."""
        return not self._failed

    def _load(self) -> bool:
        if self._model is not None:
            return True
        if self._failed:
            return False
        try:
            self._model = self._factory()
            log.info("Wake word listening for 'Hey Jarvis' (threshold %.2f).", self._thr or threshold())
            return True
        except Exception as e:
            self._failed = True
            log.warning("Wake word is on but unavailable (%s: %s). Install it with `pip install openwakeword`; "
                        "push-to-talk still works.", type(e).__name__, e)
            return False

    def _load_bg(self) -> None:
        try:
            self._load()
        finally:
            self._loading = False

    def reset(self) -> None:
        """Forget buffered audio and the model's rolling state (call while Jarvis is speaking or another
        capture runs, so its own voice or half a phrase can never add up to a hit)."""
        if not self._pending_n and not self._recent:
            return  # already clean (the main loop calls this every block while another capture runs)
        self._pending, self._pending_n = [], 0
        self._recent.clear()
        self._recent_s = 0.0
        if self._model is not None and hasattr(self._model, "reset"):
            try:
                self._model.reset()
            except Exception:
                pass

    def recent_audio(self) -> list[np.ndarray]:
        """The last ~RECENT_S of mic blocks (oldest first), for seeding the capture."""
        return [b.copy() for b in self._recent]

    def feed(self, block: np.ndarray, now: float | None = None) -> bool:
        now = now if now is not None else time.monotonic()
        block = np.asarray(block, dtype=np.float32).reshape(-1)
        self._recent.append(block.copy())
        self._recent_s += len(block) / self.sample_rate
        while self._recent_s > RECENT_S and len(self._recent) > 1:
            self._recent_s -= len(self._recent.popleft()) / self.sample_rate
        if self._model is None:
            if self._async:
                if not self._failed and not self._loading:
                    self._loading = True
                    threading.Thread(target=self._load_bg, daemon=True).start()
                return False
            if not self._load():
                return False
        self._pending.append(block)
        self._pending_n += len(block)
        hit = False
        while self._pending_n >= self._native_frame:
            buf = np.concatenate(self._pending)
            chunk, rest = buf[:self._native_frame], buf[self._native_frame:]
            self._pending, self._pending_n = ([rest] if len(rest) else []), len(rest)
            try:
                scores = self._model.predict(resample_block(chunk, self.sample_rate))
            except Exception as e:
                log.warning("Wake word model failed (%s); switching it off for this run.", e)
                self._failed, self._model = True, None
                return False
            score = max((float(v) for v in scores.values()), default=0.0) if isinstance(scores, dict) else 0.0
            self.last_score = score
            if score >= (self._thr if self._thr is not None else threshold()) and now >= self._quiet_until:
                hit = True
        if hit:
            self._quiet_until = now + self.cooldown_s
            self._pending, self._pending_n = [], 0
            if hasattr(self._model, "reset"):
                try:
                    self._model.reset()
                except Exception:
                    pass
        return hit


# --- what the speech-to-text heard after a wake-word capture ------------------------------------
# The detector can fire on a TV or a similar-sounding word, so the transcript is the second check: a
# wake capture only counts if it starts with the name. STT often writes it a little differently.
_NAMES = r"(?:jarvis|jarvus|jarvas|jervis|jarves|travis|jarvi|jarvice|jarvic)"
_WAKE_LEAD_RE = re.compile(
    rf"^\W*(?:(?:hey|hay|hi|hello|ok|okay|yo|a)\W+)?{_NAMES}\b\W*", re.IGNORECASE)


def strip_wake_phrase(transcript: str) -> tuple[bool, str]:
    """(heard_the_name, the command after it). ("Hey Jarvis, what's the weather" -> (True, "what's the weather"))."""
    m = _WAKE_LEAD_RE.match(transcript or "")
    if not m:
        return False, transcript or ""
    return True, (transcript[m.end():]).strip(" ,.!?-")
