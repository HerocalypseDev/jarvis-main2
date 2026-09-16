"""Direct window control for Jarvis (Windows only).

Thin wrapper over PyGetWindow (already a dependency — see requirements.txt, and
jarvis.py's own focus_window()) for minimize/maximize/restore/close/snap of individual
windows, arranging several windows into a layout, and saving/restoring named layouts
(persisted to the same jarvis_memory.db every other jarvis_*.py module uses).

Self-contained: no import-time dependency back on jarvis.py. pygetwindow is imported
lazily inside functions, matching the lazy-import pattern jarvis.py itself already uses
for pyautogui/pygetwindow, so importing this module never fails just because the
optional dependency isn't installed — only calling into it does, with a clear message.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import threading
from datetime import datetime
from pathlib import Path

log = logging.getLogger("jarvis.window_control")

SNAP_SIDES = (
    "left", "right", "top", "bottom",
    "top-left", "top-right", "bottom-left", "bottom-right",
    "maximize", "center",
)
ARRANGE_LAYOUTS = ("side-by-side", "grid", "cascade")


def _db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "jarvis_memory.db"


_db_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS window_layouts ("
        "name TEXT PRIMARY KEY, "
        "windows_json TEXT NOT NULL, "
        "saved_at TEXT NOT NULL)"
    )
    return conn


def _screen_size() -> tuple[int, int]:
    if sys.platform == "win32":
        import ctypes

        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return (1920, 1080)


def _pygetwindow():
    try:
        import pygetwindow as gw

        return gw
    except ImportError:
        log.warning("Install `PyGetWindow` (see requirements.txt) to control windows.")
        return None


def _find(gw, title_substring: str):
    needle = (title_substring or "").strip().lower()
    if not needle:
        return None
    return next(
        (w for w in gw.getAllWindows() if w.title and needle in w.title.lower()), None
    )


# --- single-window actions ----------------------------------------------------------
def _with_window(title: str, verb: str, action):
    gw = _pygetwindow()
    if gw is None:
        return "PyGetWindow isn't installed."
    win = _find(gw, title)
    if win is None:
        return f"No open window matching {title!r}."
    try:
        action(win)
        return f"{verb} {win.title!r}."
    except Exception as e:
        log.warning("Could not %s window %r: %s", verb.lower(), title, e)
        return f"Could not {verb.lower()} {win.title!r}: {e}"


def minimize_window(title: str) -> str:
    return _with_window(title, "Minimized", lambda w: w.minimize())


def maximize_window(title: str) -> str:
    return _with_window(title, "Maximized", lambda w: w.maximize())


def restore_window(title: str) -> str:
    return _with_window(title, "Restored", lambda w: w.restore())


def close_window(title: str) -> str:
    return _with_window(title, "Closed", lambda w: w.close())


def _snap_rect(side: str, screen_w: int, screen_h: int) -> tuple[int, int, int, int]:
    half_w, half_h = screen_w // 2, screen_h // 2
    quarter_w, quarter_h = half_w, half_h
    rects = {
        "left": (0, 0, half_w, screen_h),
        "right": (half_w, 0, screen_w - half_w, screen_h),
        "top": (0, 0, screen_w, half_h),
        "bottom": (0, half_h, screen_w, screen_h - half_h),
        "top-left": (0, 0, quarter_w, quarter_h),
        "top-right": (half_w, 0, screen_w - half_w, quarter_h),
        "bottom-left": (0, half_h, quarter_w, screen_h - half_h),
        "bottom-right": (half_w, half_h, screen_w - half_w, screen_h - half_h),
        "center": (screen_w // 4, screen_h // 4, half_w, half_h),
    }
    return rects[side]


def snap_window(title: str, side: str) -> str:
    side = (side or "").strip().lower()
    if side not in SNAP_SIDES:
        return f"{side!r} is not a known snap side ({', '.join(SNAP_SIDES)})."
    gw = _pygetwindow()
    if gw is None:
        return "PyGetWindow isn't installed."
    win = _find(gw, title)
    if win is None:
        return f"No open window matching {title!r}."
    try:
        if win.isMinimized:
            win.restore()
        if side == "maximize":
            win.maximize()
            return f"Maximized {win.title!r}."
        screen_w, screen_h = _screen_size()
        x, y, w, h = _snap_rect(side, screen_w, screen_h)
        win.restore() if win.isMaximized else None
        win.moveTo(x, y)
        win.resizeTo(w, h)
        return f"Snapped {win.title!r} to {side}."
    except Exception as e:
        log.warning("Could not snap window %r to %s: %s", title, side, e)
        return f"Could not snap {win.title!r} to {side}: {e}"


# --- multi-window arrangement ---------------------------------------------------------
def _cascade_rects(n: int, screen_w: int, screen_h: int) -> list[tuple[int, int, int, int]]:
    w, h = int(screen_w * 0.6), int(screen_h * 0.6)
    step = 40
    return [(step * i, step * i, w, h) for i in range(n)]


def _grid_rects(n: int, screen_w: int, screen_h: int) -> list[tuple[int, int, int, int]]:
    import math

    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    cell_w, cell_h = screen_w // cols, screen_h // rows
    rects = []
    for i in range(n):
        col, row = i % cols, i // cols
        rects.append((col * cell_w, row * cell_h, cell_w, cell_h))
    return rects


def _side_by_side_rects(n: int, screen_w: int, screen_h: int) -> list[tuple[int, int, int, int]]:
    col_w = screen_w // n
    return [(i * col_w, 0, col_w, screen_h) for i in range(n)]


def arrange_windows(titles: list[str], layout: str = "side-by-side") -> str:
    layout = (layout or "side-by-side").strip().lower()
    if layout not in ARRANGE_LAYOUTS:
        return f"{layout!r} is not a known layout ({', '.join(ARRANGE_LAYOUTS)})."
    titles = [t for t in (titles or []) if t]
    if len(titles) < 2:
        return "Need at least two window titles to arrange."
    gw = _pygetwindow()
    if gw is None:
        return "PyGetWindow isn't installed."

    wins = []
    missing = []
    for t in titles:
        w = _find(gw, t)
        (wins.append(w) if w is not None else missing.append(t))
    if not wins:
        return f"None of {titles} matched an open window."

    screen_w, screen_h = _screen_size()
    if layout == "side-by-side":
        rects = _side_by_side_rects(len(wins), screen_w, screen_h)
    elif layout == "grid":
        rects = _grid_rects(len(wins), screen_w, screen_h)
    else:
        rects = _cascade_rects(len(wins), screen_w, screen_h)

    placed = []
    for win, (x, y, w, h) in zip(wins, rects):
        try:
            if win.isMinimized or win.isMaximized:
                win.restore()
            win.moveTo(x, y)
            win.resizeTo(w, h)
            placed.append(win.title)
        except Exception as e:
            log.warning("Could not place window %r: %s", win.title, e)

    result = f"Arranged ({layout}): {', '.join(placed)}."
    if missing:
        result += f" No match for: {', '.join(missing)}."
    return result


# --- save/restore layouts -------------------------------------------------------------
def _snapshot_windows(gw, titles: list[str] | None) -> list[dict]:
    if titles:
        wins = [w for t in titles if (w := _find(gw, t)) is not None]
    else:
        wins = [w for w in gw.getAllWindows() if w.title and w.visible]
    snapshot = []
    for w in wins:
        try:
            snapshot.append(
                {
                    "title": w.title,
                    "left": w.left,
                    "top": w.top,
                    "width": w.width,
                    "height": w.height,
                    "is_maximized": bool(w.isMaximized),
                    "is_minimized": bool(w.isMinimized),
                }
            )
        except Exception as e:
            log.debug("Skipping window in snapshot (%s): %s", w.title, e)
    return snapshot


def save_layout(name: str, titles: list[str] | None = None) -> str:
    name = (name or "").strip()
    if not name:
        return "No layout name given."
    gw = _pygetwindow()
    if gw is None:
        return "PyGetWindow isn't installed."
    snapshot = _snapshot_windows(gw, titles)
    if not snapshot:
        return "No matching open windows to save."
    now = datetime.now().isoformat(timespec="seconds")
    with _db_lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO window_layouts (name, windows_json, saved_at) VALUES (?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET windows_json = excluded.windows_json, "
                "saved_at = excluded.saved_at",
                (name, json.dumps(snapshot), now),
            )
            conn.commit()
        finally:
            conn.close()
    return f"Saved layout {name!r} ({len(snapshot)} window(s))."


def restore_layout(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "No layout name given."
    with _db_lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT windows_json FROM window_layouts WHERE name = ?", (name,)
            ).fetchone()
        finally:
            conn.close()
    if row is None:
        return f"No saved layout named {name!r}."
    snapshot = json.loads(row[0])
    gw = _pygetwindow()
    if gw is None:
        return "PyGetWindow isn't installed."

    restored, missing = [], []
    for entry in snapshot:
        win = _find(gw, entry["title"])
        if win is None:
            missing.append(entry["title"])
            continue
        try:
            if entry["is_minimized"]:
                win.minimize()
            elif entry["is_maximized"]:
                win.maximize()
            else:
                win.restore() if (win.isMinimized or win.isMaximized) else None
                win.moveTo(entry["left"], entry["top"])
                win.resizeTo(entry["width"], entry["height"])
            restored.append(win.title)
        except Exception as e:
            log.warning("Could not restore window %r from layout: %s", entry["title"], e)

    result = f"Restored layout {name!r}: {', '.join(restored) if restored else 'nothing matched'}."
    if missing:
        result += f" Not currently open: {', '.join(missing)}."
    return result


def list_layouts() -> str:
    with _db_lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT name, windows_json, saved_at FROM window_layouts ORDER BY saved_at DESC"
            ).fetchall()
        finally:
            conn.close()
    if not rows:
        return "No saved window layouts."
    lines = []
    for name, windows_json, saved_at in rows:
        n = len(json.loads(windows_json))
        lines.append(f"{name} ({n} window(s), saved {saved_at})")
    return "\n".join(lines)


def delete_layout(name: str) -> str:
    name = (name or "").strip()
    with _db_lock:
        conn = _connect()
        try:
            cur = conn.execute("DELETE FROM window_layouts WHERE name = ?", (name,))
            conn.commit()
        finally:
            conn.close()
    return f"Deleted layout {name!r}." if cur.rowcount else f"No saved layout named {name!r}."


def list_open_windows() -> str:
    gw = _pygetwindow()
    if gw is None:
        return "PyGetWindow isn't installed."
    titles = sorted({w.title for w in gw.getAllWindows() if w.title and w.visible})
    if not titles:
        return "No visible windows found."
    return "\n".join(titles)
