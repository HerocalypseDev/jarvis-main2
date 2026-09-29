"""Tolerant numeric settings from the environment (audit 2026-09-29).

Module-level `int(os.environ.get(X) or D)` crashed the import (so Jarvis would not start at all) when .env held
a value that isn't a whole number: the dashboard Settings page accepts any number, so saving "12.5" for a
whole-number setting, or a typo, bricked the next start. These return the default on a bad value and log it.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("jarvis.env")


def _raw(key: str) -> str:
    return (os.environ.get(key) or "").strip()


def env_float(key: str, default: float) -> float:
    raw = _raw(key)
    if not raw:
        return float(default)
    try:
        return float(raw)
    except ValueError:
        log.warning("Setting %s=%r isn't a number; using %s.", key, raw, default)
        return float(default)


def env_int(key: str, default: int) -> int:
    raw = _raw(key)
    if not raw:
        return int(default)
    try:
        return int(raw)
    except ValueError:
        try:
            return int(round(float(raw)))      # "12.5" -> 12, "40.0" -> 40
        except ValueError:
            log.warning("Setting %s=%r isn't a whole number; using %s.", key, raw, default)
            return int(default)
