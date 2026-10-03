"""What each request carries besides the request itself (2026-10-03, owner: "Jarvis is slow and brings up the last thing
I talked about").

Measured in the owner's debug reports: every model call sent ~15,700 tokens, of which up to 16,000 characters were the
full text of every saved skill (40+ with the Pro pack) and up to 8 earlier exchanges, whatever the request was. Two
effects: slower answers, and answers that drifted back to the previous topic. This module picks the parts that matter:

- skills: a short index always; the full steps only for the one or two skills the request is about.
- conversation: the last two exchanges always; older ones only when they share real words with the request, or the
  request clearly refers back ("it", "that", "again", "what about...").

Pure functions (no jarvis import), so they are cheap to test and never break a command.
"""
from __future__ import annotations

import re

STOP = frozenset((
    "a an the and or but if then so to of in on at for from by with about as is are was were be been being am do does did "
    "done have has had i me my mine you your yours he she it its we our they them their this that these those there here "
    "what which who whom whose when where why how can could would should will shall may might must just also very really "
    "please jarvis hey okay ok yes no not now today tomorrow tonight some any all more most much many one two get got make "
    "made let lets tell say said know like want need go going thing things time".split()))
_WORD_RE = re.compile(r"[a-z0-9']+")
REFERS_BACK_RE = re.compile(
    r"^\s*(?:and|also|then|so|but|what about|how about|ok(?:ay)?|yes|yeah|yep|no|nope|sure|do it|go ahead|same|again)\b"
    r"|\b(?:it|that|this|those|them|these|again|earlier|before|previous(?:ly)?|the last one|the same|you said|you just)\b",
    re.I)


def _stem(w: str) -> str:
    for end in ("ing", "ed", "es", "s"):
        if len(w) > len(end) + 3 and w.endswith(end):
            return w[: -len(end)]
    return w


def content_words(text: str) -> set[str]:
    return {_stem(w.strip("'")) for w in _WORD_RE.findall((text or "").lower())
            if len(w.strip("'")) >= 3 and w.strip("'") not in STOP and not w.isdigit()}


def refers_back(query: str) -> bool:
    return bool(REFERS_BACK_RE.search(query or ""))


def pick_history(messages: list[dict], query: str, keep_last_exchanges: int = 2) -> list[dict]:
    """messages: user/assistant pairs, oldest first. Keeps the newest exchanges, plus older exchanges that share a
    content word with the query; everything when the query refers back to something earlier."""
    if not query or refers_back(query) or len(messages) <= keep_last_exchanges * 2:
        return list(messages)
    keep_from = len(messages) - keep_last_exchanges * 2
    want = content_words(query)
    out = []
    i = 0
    while i < keep_from:
        pair = messages[i:i + 2]
        if len(pair) == 2 and pair[0].get("role") == "user":
            text = " ".join(str(m.get("content") or "") for m in pair)
            if want & content_words(text):
                out.extend(pair)
            i += 2
        else:  # odd shape: keep the old behaviour for the rest rather than break alternation
            return list(messages)
    return out + list(messages[keep_from:])


def skills_index(skills: list[dict], max_chars: int = 2600) -> str:
    """One short line per skill (name + start of its description), shortest-first when space runs out."""
    if not skills:
        return ""
    lines, used, left = [], 0, 0
    for s in skills:
        desc = " ".join(str(s.get("description") or "").split())
        line = f"- {s['name']}: {desc[:90]}{'...' if len(desc) > 90 else ''}"
        if used + len(line) > max_chars:
            left += 1
            continue
        lines.append(line)
        used += len(line) + 1
    more = f"\n(+{left} more; the skills tool lists them all)" if left else ""
    return "\n".join(lines) + more


def relevant_skills(skills: list[dict], query: str, limit: int = 2) -> list[dict]:
    """The skills a request is about: shared content words with the name/description (a word naming the skill
    counts double). Nothing when no skill clearly matches."""
    want = content_words(query)
    if not want:
        return []
    scored = []
    for s in skills:
        name_words = content_words(str(s["name"]).replace("_", " "))
        desc_words = content_words(s.get("description") or "")
        name_hits, desc_hits = len(want & name_words), len(want & desc_words)
        score = 2 * name_hits + desc_hits
        if name_hits or desc_hits >= 3:  # the skill's own name, or three description words: loose matches mislead
            scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return []
    best = scored[0][0]
    return [s for sc, s in scored[:limit] if sc == best]  # a weaker second match is more noise than help


# --- Phase C (2026-10-03): the "main memory" line. Every request checks reminders, jobs, tasks and older conversations
# for things related to it; the calendar only when the request is about time, plans or people (owner's "smart mix").
# Audit 2026-10-03: "when", "what time", "date", "week" and "morning" sent "when was the Eiffel Tower built" and
# "what time does the shop close" to the calendar (up to a few seconds' wait on a cache miss); only words that are
# about the owner's own plans count now.
TIME_PLANS_RE = re.compile(
    r"\b(?:free|busy|available|availability|schedule|calendar|meeting|meetings|appointment|plans?|planned|event|"
    r"tonight|tomorrow|weekend|this week|next week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"am i doing|do i have|deadline|exam|lecture|trip|birthday)\b", re.I)
MESSAGES_RE = re.compile(r"\b(?:e-?mails?|mail|inbox|messages?|texts?|texted|replied|reply|wrote|sent|whatsapp|telegram|"
                         r"dm|asked me|told me)\b", re.I)


def wants_calendar(query: str, people: set[str] | frozenset = frozenset()) -> bool:
    q = query or ""
    return bool(TIME_PLANS_RE.search(q)) or any(re.search(rf"\b{re.escape(p)}\b", q, re.I) for p in people)


def mentions_messages(query: str) -> bool:
    return bool(MESSAGES_RE.search(query or ""))


def related(text: str, query_words: set[str], need: int = 1) -> bool:
    return len(query_words & content_words(text)) >= need


def calendar_lines(raw: str, now, until, limit: int = 8) -> list[str] | None:
    """Calendar MCP list-events JSON -> "Sun 5 Oct 3:00 PM Title" lines (day included: this covers a week)."""
    import json
    from jarvis_briefing import _when
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    events = data.get("events") if isinstance(data, dict) else data
    if not isinstance(events, list):
        return None
    out = []
    for e in events:
        if not isinstance(e, dict) or e.get("status") == "cancelled":
            continue
        title = " ".join(str(e.get("summary") or "(untitled)").split())[:70]
        start = e.get("start") or {}
        if start.get("dateTime"):
            s = _when(start["dateTime"])
            if s is None or s >= until:
                continue
            end = _when((e.get("end") or {}).get("dateTime") or start["dateTime"])
            if end is not None and end <= now:
                continue
            out.append((s, s.strftime("%a %d %b ") + s.strftime("%I:%M %p").lstrip("0") + f" {title}"))
        elif start.get("date"):
            try:
                from datetime import datetime as _dt
                d = _dt.fromisoformat(start["date"])
            except ValueError:
                continue
            if d.date() >= until.date():
                continue
            out.append((d, d.strftime("%a %d %b") + f" all day: {title}"))
    out.sort(key=lambda x: x[0])
    return [line for _, line in out[:limit]]
