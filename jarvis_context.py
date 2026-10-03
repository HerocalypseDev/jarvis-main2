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
