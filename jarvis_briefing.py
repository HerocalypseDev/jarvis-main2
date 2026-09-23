"""Morning briefing v2 and "what's urgent?" (2026-09-23).

One composition used by voice ("good morning", "what's urgent"), the dashboard Home card
(GET /api/briefing) and anything else that wants it. Pure: jarvis.py passes in fetchers that read
existing data (calendar MCP, Gmail MCP, autonomy, reminders, sleep log, weather, pending
confirmation); each fetcher returns a list of short lines, or None/[] for "nothing" or "not
available". A fetcher that fails or times out is dropped, never guessed at. Empty sections are
omitted; the spoken version is capped.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from typing import Callable

log = logging.getLogger("jarvis.briefing")

FETCH_TIMEOUT_S = 15
SPEECH_MAX_CHARS = 700
SPEECH_ITEMS_PER_SECTION = 3

# (key, title) in the order they're shown and spoken. "urgent" is the needs-you subset.
SECTIONS = {
    "morning": [
        ("pending", "Waiting for your confirmation"),
        ("weather", "Weather"),
        ("calendar", "Today's calendar"),
        ("deadlines", "Deadlines"),
        ("mail", "Important unread mail"),
        ("reminders", "Reminders today"),
        ("needs_you", "Autonomy items to review"),
        ("failed", "Failed tasks"),
        ("sleep", "Sleep"),
        ("system", "System"),
    ],
    "urgent": [
        ("pending", "Waiting for your confirmation"),
        ("deadlines", "Deadlines"),
        ("calendar", "Coming up"),
        ("mail", "Important unread mail"),
        ("reminders", "Reminders soon"),
        ("needs_you", "Autonomy items to review"),
        ("failed", "Failed tasks"),
        ("system", "System"),
    ],
}


def compose(kind: str, fetchers: dict[str, Callable[[], list[str] | None]],
            now: datetime | None = None, timeout: float = FETCH_TIMEOUT_S) -> dict:
    kind = kind if kind in SECTIONS else "urgent"
    now = now or datetime.now()
    wanted = [(k, t) for k, t in SECTIONS[kind] if k in fetchers]
    results: dict[str, list[str]] = {}
    ex = ThreadPoolExecutor(max_workers=max(1, len(wanted)))
    futs = {k: ex.submit(fetchers[k]) for k, _ in wanted}
    wait(futs.values(), timeout=timeout)
    for k, f in futs.items():
        if not f.done():
            log.info("Briefing: %s timed out; left out.", k)
            continue
        try:
            items = [str(i).strip() for i in (f.result() or []) if str(i).strip()]
        except Exception as e:
            log.warning("Briefing: %s failed (%s); left out.", k, e)
            continue
        if items:
            results[k] = items
    ex.shutdown(wait=False, cancel_futures=True)  # a stuck fetcher never holds up the answer
    sections = [{"key": k, "title": t, "items": results[k]} for k, t in wanted if k in results]
    return {"kind": kind, "generated_at": now.isoformat(timespec="seconds"),
            "sections": sections, "speech": speech(kind, sections, now)}


def speech(kind: str, sections: list[dict], now: datetime | None = None) -> str:
    now = now or datetime.now()
    if kind == "morning":
        part = "morning" if now.hour < 12 else ("afternoon" if now.hour < 18 else "evening")
        opener = f"Good {part}."
    else:
        opener = ""
    if not sections:
        return (opener + " Nothing needs you right now.").strip()
    lines = [opener] if opener else []
    for s in sections:
        items = s["items"]
        shown = [i.rstrip(" .;") for i in items[:SPEECH_ITEMS_PER_SECTION]]  # no "rain.." when joined
        more = len(items) - len(shown)
        line = f"{s['title']}: " + "; ".join(shown) + (f"; and {more} more" if more > 0 else "") + "."
        if len(" ".join(lines + [line])) > SPEECH_MAX_CHARS and len(lines) > (1 if opener else 0):
            lines.append("There's more on the dashboard.")
            break
        lines.append(line)
    return " ".join(lines)


# --- formatters for raw data jarvis.py fetches (pure, unit-tested) --------------------------------

def _when(iso: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone().replace(tzinfo=None) if d.tzinfo else d


def _hm(d: datetime) -> str:
    return d.strftime("%I:%M %p").lstrip("0")


def calendar_items(raw: str, now: datetime, until: datetime) -> list[str] | None:
    """Calendar MCP (@cocal/google-calendar-mcp) list-events JSON -> "9:30 AM Standup" lines, with
    overlapping timed events flagged. None if the text isn't that JSON (error, not connected)."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    events = data.get("events") if isinstance(data, dict) else data
    if not isinstance(events, list):
        return None
    timed, out = [], []
    for e in events:
        if not isinstance(e, dict) or e.get("status") == "cancelled":
            continue
        title = (e.get("summary") or "(untitled)").strip()[:80]
        start, end = e.get("start") or {}, e.get("end") or {}
        if start.get("dateTime"):
            s, en = _when(start["dateTime"]), _when(end.get("dateTime") or start["dateTime"])
            if s is None or en is None or en <= now or s >= until:
                continue
            timed.append((s, en, title))
        elif start.get("date"):
            out.append(f"all day: {title}")
    timed.sort()
    for i, (s, en, title) in enumerate(timed):
        clash = any(s < en2 and s2 < en for j, (s2, en2, _) in enumerate(timed) if j != i)
        out.append(f"{'now' if s <= now else _hm(s)} {title}" + (" (overlaps another event)" if clash else ""))
    return out


def mail_items(parsed: list[dict], limit: int = 5) -> list[str]:
    """Output of jarvis_sleep_mail.parse_search -> "Sender: subject" lines."""
    out = []
    for m in parsed[:limit]:
        who = (m.get("from") or m.get("sender") or "someone").split("<")[0].strip().strip('"') or m.get("sender", "")
        out.append(f"{who[:40]}: {(m.get('subject') or '(no subject)')[:80]}")
    return out


def deadline_items(commitments: list[dict], now: datetime, horizon_h: float = 24) -> list[str]:
    out = []
    for c in commitments:
        due = _when(c.get("deadline_iso") or "")
        if due is None or due > now + timedelta(hours=horizon_h):
            continue
        what = (c.get("description") or c.get("title") or "a commitment").strip()[:80]
        if due < now:
            out.append(f"overdue: {what}")
        else:
            out.append(f"{what}, due {'today' if due.date() == now.date() else 'tomorrow'} at {_hm(due)}")
    return out


def sleep_items(stats: dict, now: datetime) -> list[str]:
    out = []
    today = now.date().isoformat()
    last = next((d for d in reversed(stats.get("daily") or []) if d.get("date") == today and d.get("hours")), None)
    goal = stats.get("goal_hours")
    if last:
        out.append(f"last night {last['hours']:.1f} hours" + (f" (goal {goal:g})" if goal else ""))
    debt = (stats.get("week") or {}).get("debt_hours")
    if debt and debt >= 1:
        out.append(f"{debt:g} hours of sleep debt this week")
    return out
