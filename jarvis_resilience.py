"""Keeps Jarvis alive when the microphone loop fails (2026-10-07, owner: "jarvis keeps closing anyhow").

The main loop used to have no safety net: a device hiccup (headphones or Bluetooth unplugged, the PC
waking from sleep, Windows audio restarting) or any error raised inside it ended `main()` and with it the
whole program. `supervise` runs one listening session at a time and starts a new one after a failure,
backing off, writing the reason to a crash log, and saying once per outage that it is back.

Pure helpers (no jarvis import) so the behaviour is testable without audio hardware."""

from __future__ import annotations

import time
import traceback
from pathlib import Path

BACKOFF_START_S = 2.0
BACKOFF_MAX_S = 30.0
HEALTHY_AFTER_S = 60.0       # a session that ran this long was fine: its failure starts a new outage
ANNOUNCE_GAP_S = 600.0       # at most one spoken "back" notice per 10 minutes (a flapping device)
CRASH_LOG_MAX_BYTES = 256 * 1024


def backoff_seconds(failures: int) -> float:
    """2, 4, 8, 16, 30, 30... seconds after the 1st, 2nd, ... consecutive failure."""
    if failures <= 0:
        return 0.0
    return min(BACKOFF_MAX_S, BACKOFF_START_S * (2 ** (failures - 1)))


def write_crash(path: Path, label: str, exc: BaseException | None = None, now: float | None = None) -> None:
    """Append one entry (time, label, traceback) to the crash log; the file is cut to its newest half when
    it grows past CRASH_LOG_MAX_BYTES. Never raises."""
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now if now is not None else time.time()))
        body = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) if exc else ""
        entry = f"[{stamp}] {label}\n{body}\n"
        path = Path(path)
        if path.exists() and path.stat().st_size > CRASH_LOG_MAX_BYTES:
            data = path.read_text(encoding="utf-8", errors="replace")
            path.write_text(data[len(data) // 2:], encoding="utf-8")
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass


def reset_portaudio() -> None:
    """Make PortAudio re-read the device list (a device unplugged or added while running is otherwise
    not seen). Safe to call when sounddevice is missing or the reset isn't supported."""
    try:
        import sounddevice as sd
        sd._terminate()
        sd._initialize()
    except Exception:
        pass


def supervise(run_session, *, on_failure=None, on_recovered=None, sleep=time.sleep, monotonic=time.monotonic,
              keep_going=lambda: True, max_sessions: int | None = None) -> int:
    """Run `run_session()` (one microphone session that normally never returns) again and again.

    - KeyboardInterrupt / SystemExit end it (a deliberate stop): returns 0.
    - Any other exception: `on_failure(exc, failures, wait_s)`, sleep with backoff, start a new session.
    - `on_recovered(failures)` is called once per outage, as soon as a new session has its microphone open.
    `run_session(started)` must call `started()` when the microphone is open.
    `keep_going`/`max_sessions` only exist so tests can stop the loop."""
    failures = 0
    sessions = 0
    outage_announced = True   # nothing to announce until something failed
    while keep_going():
        if max_sessions is not None and sessions >= max_sessions:
            return 0
        sessions += 1
        began = monotonic()

        def started() -> None:
            nonlocal outage_announced
            if failures and not outage_announced:
                outage_announced = True
                if on_recovered is not None:
                    try:
                        on_recovered(failures)
                    except Exception:
                        pass

        try:
            run_session(started)
            return 0  # a session that ends normally is a deliberate stop
        except (KeyboardInterrupt, SystemExit):
            return 0
        except Exception as e:  # noqa: BLE001 - the whole point: nothing here may end Jarvis
            ran = monotonic() - began
            failures = 1 if ran >= HEALTHY_AFTER_S else failures + 1
            outage_announced = False
            wait = backoff_seconds(failures)
            if on_failure is not None:
                try:
                    on_failure(e, failures, wait)
                except Exception:
                    pass
            sleep(wait)
    return 0


class Announcer:
    """Decides whether a "microphone is back" notice is spoken: at most once per ANNOUNCE_GAP_S."""

    def __init__(self, monotonic=time.monotonic):
        self._mono = monotonic
        self._last: float | None = None

    def should_speak(self) -> bool:
        now = self._mono()
        if self._last is not None and now - self._last < ANNOUNCE_GAP_S:
            return False
        self._last = now
        return True
