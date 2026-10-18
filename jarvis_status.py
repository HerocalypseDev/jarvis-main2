"""Real status checks: "is my Windows MCP working?" is answered from a check, never from a guess.

2026-10-18 debug report: asked whether Windows-MCP worked, Jarvis listed node/python processes, tried localhost:3000,
scanned ports 3000/8080/5000 and found a Windows service called McpManagementService, then said the server was "still
not up". Windows-MCP runs over stdio (uvx), not on a port, so none of that could tell; Jarvis already tracks the real
connection. The owner then asked for the same for everything else Jarvis can't check.

Pure module (never imports jarvis.py). jarvis.py builds the list of `Check`s each time (tool servers come and go) and
hands it in. Each check returns `(state, detail)`; a check that raises or doesn't answer in time is UNKNOWN with the
reason, never "working". A question about something with no check gets an honest "I can't check that".
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout
from dataclasses import dataclass, field
from typing import Callable

WORKING, DOWN, OFF, UNKNOWN = "working", "not working", "off", "unknown"
STATES = (WORKING, DOWN, OFF, UNKNOWN)
CHECK_TIMEOUT_S = 12.0


@dataclass
class Check:
    key: str
    label: str
    aliases: tuple[str, ...]
    fn: Callable[[], tuple[str, str]]
    group: str = "other"
    everything: bool = True        # included in "is everything working?"
    extra: dict = field(default_factory=dict)


def norm(text: str) -> str:
    t = (text or "").lower().replace("’", "'")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# Words that make a sentence about whether something works.
_STATUS_WORD_RE = re.compile(
    r"\b(?:work|works|working|worked|workin|functional|functioning|up|running|connected|connect(?:ing|ion)?|online|"
    r"offline|down|broken|broke|fixed|ok|okay|fine|alive|reachable|status|healthy|health|failing|failed|fail|"
    r"responding|responsive|live|active|dead|crashed|stuck|available)\b")
_QUESTION_RE = re.compile(
    r"\A\s*(?:hey |ok |okay )?(?:jarvis )?(?:is|are|does|do|did|has|have|can|could|was|were|check|test|"
    r"what's|what is|whats|how's|how is|hows|tell me|see if|find out|verify|confirm)\b|\b(?:check|test|verify|confirm) "
    r"(?:if|whether|that|the|my)\b|\bstatus\b")
# "is everything working", "what's broken", "any problems", "system status", "check all your systems"
_EVERYTHING_RE = re.compile(
    r"\b(?:is|are) (?:everything|all|all your (?:systems|services|tools|parts)|all of it) (?:working|ok|okay|fine|"
    r"up|running|good|connected)|\bwhat(?:'s| is| are)? (?:not working|broken|down|failing)\b|\bany(?:thing)? "
    r"(?:problems?|issues?|broken|down|failing)\b|\b(?:system|full|overall|status) (?:status|report|check)\b|"
    r"\bcheck (?:all|everything|all your|your) (?:systems|services|tools|connections|parts)\b|"
    r"\bwhat(?:'s| is) (?:working|the status of everything)\b")
# Requests that only mention a component on the way to doing something with it ("open whatsapp", "send an email").
_ACTION_RE = re.compile(
    r"\A\s*(?:hey |ok |okay )?(?:jarvis )?(?:please )?(?:open|send|write|read|reply|search|find|play|start|turn|"
    r"switch|set|make|create|add|delete|remove|close|show|book|schedule|draft|call|ring|text|message)\b")
MAX_WORDS = 18


def is_status_question(text: str) -> bool:
    t = norm(text)
    if not t or len(t.split()) > MAX_WORDS:
        return False
    if _EVERYTHING_RE.search(t):
        return True
    if _ACTION_RE.search(t) and not re.search(r"\b(?:check|test|verify|see) (?:if|whether)\b", t):
        return False
    asks = (text or "").strip().endswith("?") or bool(_QUESTION_RE.search(t))
    return bool(asks and _STATUS_WORD_RE.search(t))


def asks_everything(text: str) -> bool:
    return bool(_EVERYTHING_RE.search(norm(text)))


def match(text: str, checks: list[Check]) -> list[str]:
    """Keys of the checks the text names, longest alias first, so "browser tabs" isn't also "browser"."""
    t = " " + norm(text) + " "
    spans: list[tuple[int, int, str]] = []
    for c in checks:
        for alias in sorted({norm(a) for a in (c.label, c.key, *c.aliases) if a}, key=len, reverse=True):
            for m in re.finditer(r"(?<= )" + re.escape(alias) + r"(?= )", t):
                spans.append((m.start(), m.end(), c.key))
    spans.sort(key=lambda s: (-(s[1] - s[0]), s[0]))
    kept: list[tuple[int, int, str]] = []
    for s in spans:
        if any(k[0] <= s[0] and s[1] <= k[1] for k in kept):
            continue
        kept.append(s)
    out: list[str] = []
    for _a, _b, key in sorted(kept):
        if key not in out:
            out.append(key)
    return out


def run(checks: list[Check], keys: list[str] | None = None, timeout: float = CHECK_TIMEOUT_S) -> list[dict]:
    """Runs the checks side by side. Never raises; a failed or slow check is UNKNOWN with why."""
    chosen = [c for c in checks if (keys is None and c.everything) or (keys is not None and c.key in keys)]
    if keys:
        chosen.sort(key=lambda c: keys.index(c.key))
    out: list[dict] = []
    if not chosen:
        return out
    ex = ThreadPoolExecutor(max_workers=min(8, len(chosen)))
    try:
        futs = [(c, ex.submit(c.fn)) for c in chosen]
        deadline = time.monotonic() + timeout
        for c, fut in futs:
            started = time.monotonic()
            try:
                state, detail = fut.result(timeout=max(0.1, deadline - time.monotonic()))
                if state not in STATES:
                    state, detail = UNKNOWN, f"the check gave an unclear answer ({state!r})"
            except _Timeout:
                state, detail = UNKNOWN, f"the check didn't answer within {timeout:.0f} seconds"
            except Exception as e:  # noqa: BLE001
                state, detail = UNKNOWN, f"the check itself failed ({type(e).__name__}: {str(e)[:120]})"
            out.append({"key": c.key, "label": c.label, "group": c.group, "state": state,
                        "detail": _clean(detail), "ms": int((time.monotonic() - started) * 1000)})
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return out


def _clean(detail: str) -> str:
    d = re.sub(r"[\x00-\x1f\x7f]+", " ", str(detail or "")).strip()
    return d[:300]


def _line(r: dict) -> str:
    detail = r["detail"].rstrip(".")
    if r["state"] == WORKING:
        return f"{r['label']} is working" + (f": {detail}" if detail else "")
    if r["state"] == DOWN:
        return f"{r['label']} is NOT working" + (f": {detail}" if detail else "")
    if r["state"] == OFF:
        return f"{r['label']} is off" + (f": {detail}" if detail else "")
    return f"I couldn't tell whether {r['label']} works" + (f" ({detail})" if detail else "")


def render(results: list[dict], everything: bool = False, full: bool = False) -> str:
    """Spoken answer. One or two things: a sentence each. Everything: problems first, then the rest by name."""
    if not results:
        return "I don't have a way to check that."
    if not everything or len(results) <= 2:
        return " ".join(_line(r) + "." for r in results)
    bad = [r for r in results if r["state"] == DOWN]
    unk = [r for r in results if r["state"] == UNKNOWN]
    ok = [r["label"] for r in results if r["state"] == WORKING]
    off = [r["label"] for r in results if r["state"] == OFF]
    parts = []
    if bad:
        parts.append(f"{len(bad)} thing{'s are' if len(bad) > 1 else ' is'} not working: "
                     + "; ".join(f"{r['label']} ({r['detail'].rstrip('.')})" for r in bad) + ".")
    else:
        parts.append("Everything I can check is working.")
    if unk:
        parts.append("I couldn't check " + "; ".join(f"{r['label']} ({r['detail'].rstrip('.')})" for r in unk) + ".")
    if ok:
        parts.append("Working: " + ", ".join(ok) + ".")
    if off and full:
        parts.append("Off or not set up: " + ", ".join(off) + ".")
    elif off:
        parts.append(f"{len(off)} more {'are' if len(off) > 1 else 'is'} switched off or not set up "
                     "(ask me about one by name).")
    return " ".join(parts)


def no_check_reply(text: str, checks: list[Check]) -> str:
    return ("I don't have a check for that, so I can't say whether it's working, and I won't guess. "
            "Things I can really check: " + ", ".join(c.label for c in checks) + ".")


def catalogue(checks: list[Check]) -> str:
    return "\n".join(f"- {c.key}: {c.label}" for c in checks)
