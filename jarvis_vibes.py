"""Context-aware anime-style reactions for the *text* of a reply (dashboard, phone).

Opt-in (`vibe_mode` tool or JARVIS_VIBES=1). Purely local and deterministic: it picks a kaomoji
plus a short quip from the situation (greeting, thanks, error, success, late night...). It only
decorates displayed text; the spoken reply and audit data are never changed, so no emoticon is
read aloud. No images or network fetches; memes are text-only on purpose.
"""

from __future__ import annotations

import os
import random
import re
from datetime import datetime

_enabled: bool | None = None

_REACTIONS = {
    "error": ["(´；ω；`) That one fought back.", "(ﾉ°Д°)ﾉ Plot twist: it broke."],
    "thanks": ["(≧▽≦) Anytime!", "ヾ(＾∇＾) Always happy to help."],
    "greeting": ["(｡･ω･｡)ﾉ♡ Yo!", "＼(^o^)／ Welcome back."],
    "success": ["(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧ Nailed it.", "(⌐■_■) Mission complete."],
    "late": ["(￣ω￣) It's late, don't forget to rest."],
    "funny": ["(¬‿¬) Heh."],
}
_ERR = re.compile(r"\b(error|failed|couldn't|could not|can't|unable|not found|problem)\b", re.I)
_OK = re.compile(r"\b(done|saved|created|opened|finished|started|sent|complete|enabled|wrote)\b", re.I)
_THANKS = re.compile(r"\b(thanks|thank you|thx|cheers)\b", re.I)
_HELLO = re.compile(r"^\s*(hi|hey|hello|yo|good (morning|evening|afternoon))\b", re.I)
_FUN = re.compile(r"\b(lol|haha|joke|meme|funny)\b", re.I)


def is_enabled() -> bool:
    if _enabled is not None:
        return _enabled
    return os.environ.get("JARVIS_VIBES", "0").strip().lower() in ("1", "true", "yes")


def set_enabled(on: bool) -> str:
    global _enabled
    _enabled = bool(on)
    return "Vibe mode on: replies in text get a little anime reaction." if on else "Vibe mode off."


def pick_reaction(transcript: str, reply: str, now: datetime | None = None) -> str | None:
    now = now or datetime.now()
    t, r = transcript or "", reply or ""
    if _THANKS.search(t):
        key = "thanks"
    elif _HELLO.search(t):
        key = "greeting"
    elif _FUN.search(t):
        key = "funny"
    elif _ERR.search(r):
        key = "error"
    elif now.hour < 5 and len(r) < 400:
        key = "late"
    elif _OK.search(r):
        key = "success"
    else:
        return None
    return random.choice(_REACTIONS[key])


def decorate(transcript: str, reply: str) -> str:
    """The reply with a reaction line appended, or unchanged when off / nothing fits."""
    if not reply or not is_enabled():
        return reply
    reaction = pick_reaction(transcript, reply)
    return f"{reply}\n\n{reaction}" if reaction else reply
