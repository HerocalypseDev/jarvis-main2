"""Chief-of-staff second wave (2026-09-23): pure helpers for reply style, quiet hours, the daily
spend alert and meeting heads-ups. jarvis.py does the wiring (prompt line, notification gate,
scheduler tick, calendar/Gmail calls); everything here is side-effect free and unit-tested.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, time as dtime, timedelta

# --- sticky reply style --------------------------------------------------------------------------
REPLY_STYLES = ("normal", "brief", "detailed")
_STYLE_LINES = {
    "brief": "\n\nReply style (the user's standing choice): brief. One or two short sentences unless they ask for more.",
    "detailed": "\n\nReply style (the user's standing choice): detailed. Fuller explanations and context are welcome.",
}


def reply_style_line(style: str | None) -> str:
    return _STYLE_LINES.get((style or "").strip().lower(), "")


def parse_reply_style(text: str) -> str | None:
    """"be brief from now on" -> brief, "more detailed answers" -> detailed, "normal answers" -> normal."""
    low = (text or "").lower()
    if re.search(r"\b(normal|regular|default|usual)\b", low):
        return "normal"
    if re.search(r"\b(brief|short|shorter|concise|terse)\b", low):
        return "brief"
    if re.search(r"\b(detailed|longer|thorough|more detail|explain more)\b", low):
        return "detailed"
    return None


# --- quiet hours ---------------------------------------------------------------------------------
def parse_quiet_hours(spec: str | None) -> tuple[dtime, dtime] | None:
    """"22:00-07:00" or "22-7" -> (start, end); None when empty or malformed."""
    m = re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*", spec or "")
    if not m:
        return None
    h1, m1, h2, m2 = int(m[1]), int(m[2] or 0), int(m[3]), int(m[4] or 0)
    if not (h1 < 24 and h2 < 24 and m1 < 60 and m2 < 60) or (h1, m1) == (h2, m2):
        return None
    return dtime(h1, m1), dtime(h2, m2)


def in_quiet_hours(spec: str | None, now: datetime) -> bool:
    span = parse_quiet_hours(spec)
    if not span:
        return False
    start, end = span
    t = now.time()
    return start <= t < end if start < end else (t >= start or t < end)  # crosses midnight


# --- daily spend alert ---------------------------------------------------------------------------
def budget_alert(spent_today: float, budget: float, already_alerted_on: str | None, today: str) -> str | None:
    """The alert text, once per day, when today's estimated spend reaches the budget."""
    if budget <= 0 or spent_today < budget or already_alerted_on == today:
        return None
    return (f"Heads up: I've used about ${spent_today:.2f} of API credit today, past your "
            f"${budget:.2f} daily budget. The Usage page has the breakdown.")


# --- meeting heads-up ----------------------------------------------------------------------------
def _local(iso: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone().replace(tzinfo=None) if d.tzinfo else d


def meetings_starting(raw: str, now: datetime, within_min: float, own: set[str] | None = None) -> list[dict]:
    """Calendar MCP list-events JSON -> timed, non-cancelled events starting within `within_min`
    minutes that you haven't declined: [{"id", "title", "start", "attendees": [(name, email)]}]."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    events = data.get("events") if isinstance(data, dict) else data
    out = []
    own = {e.lower() for e in (own or set())}
    for e in events if isinstance(events, list) else []:
        if not isinstance(e, dict) or e.get("status") == "cancelled":
            continue
        start = _local((e.get("start") or {}).get("dateTime") or "")
        if start is None or not (now <= start <= now + timedelta(minutes=within_min)):
            continue
        people, declined = [], False
        for a in e.get("attendees") or []:
            email = (a.get("email") or "").lower()
            if a.get("self") or email in own:
                declined = declined or a.get("responseStatus") == "declined"
                continue
            if email and not a.get("resource"):
                people.append(((a.get("displayName") or email.split("@")[0]).strip(), email))
        if declined:
            continue
        out.append({"id": e.get("id") or f"{e.get('summary')}@{start.isoformat()}",
                    "title": (e.get("summary") or "(untitled)").strip()[:80], "start": start, "attendees": people})
    return out


def headsup_text(meeting: dict, now: datetime, mail_lines: list[str] | None = None) -> str:
    mins = max(1, round((meeting["start"] - now).total_seconds() / 60))
    names = [n for n, _ in meeting["attendees"][:3]]
    more = len(meeting["attendees"]) - len(names)
    who = (" with " + ", ".join(names) + (f" and {more} more" if more > 0 else "")) if names else ""
    text = f"In {mins} minute{'s' if mins != 1 else ''}: {meeting['title']}{who}."
    if mail_lines:
        text += " Recent mail: " + "; ".join(mail_lines[:3]) + "."
    return text
