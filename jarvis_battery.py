"""Battery-aware background work (2026-09-27, feature batch A5).

On battery (not plugged in) the scheduler asks `level()` every tick:
  ok        normal
  low       <= JARVIS_BATTERY_LOW_PCT (20): autonomy ticks every 5 min instead of every minute,
            network scan every 5x its interval
  critical  <= JARVIS_BATTERY_CRITICAL_PCT (10): autonomy every 15 min, network scan paused,
            non-urgent proactive speech held until the user next talks to Jarvis
`transition()` says what to announce, once per downward crossing (and once when power is back).
Nothing is killed, nothing hibernates. Desktops (no battery) are always "ok".
"""

from __future__ import annotations

import os

_state = {"level": "ok"}
AUTONOMY_EVERY_S = {"ok": 0, "low": 300, "critical": 900}
NETSCAN_FACTOR = {"ok": 1, "low": 5, "critical": 0}  # 0 = paused


def _pct(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


HYSTERESIS_PCT = 3  # climbing back out of a level needs this much headroom (no flapping at 20/21%)


def classify(percent, plugged, current: str = "ok") -> str:
    if percent is None or plugged:
        return "ok"
    crit, low = _pct("JARVIS_BATTERY_CRITICAL_PCT", 10), _pct("JARVIS_BATTERY_LOW_PCT", 20)
    if percent <= crit or (current == "critical" and percent <= crit + HYSTERESIS_PCT):
        return "critical"
    if percent <= low or (current in ("low", "critical") and percent <= low + HYSTERESIS_PCT):
        return "low"
    return "ok"


def read() -> tuple[float | None, bool | None]:
    try:
        import psutil
        b = psutil.sensors_battery()
        return (b.percent, b.power_plugged) if b is not None else (None, None)
    except Exception:
        return None, None


def transition(new: str) -> str | None:
    """Updates the stored level; returns a line to announce, or None."""
    old, _state["level"] = _state["level"], new
    if new == old:
        return None
    if new == "critical":
        return "Battery is very low. I've paused background scanning and I'll hold non-urgent announcements."
    if new == "low" and old == "ok":
        return "Battery low; reducing background work."
    if new == "ok":
        return "Power's back to normal, so background work is back to its usual pace."
    return None  # critical -> low while charging back up: nothing worth saying


def current() -> str:
    return _state["level"]


def enabled() -> bool:
    return str(os.environ.get("JARVIS_BATTERY_SAVER", "1")).lower() not in ("0", "false", "no", "off")
