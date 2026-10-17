"""Phone calls to the owner through CallMeBot's free Telegram call service (2026-10-17, owner request).

CallMeBot rings the owner's Telegram app and reads a short message aloud. It is one-way (no talking back) and an
unofficial free service with no guarantee, so a call is always an extra alert, never the only one.

Rules (owner's choice: own number only, urgent alerts only):
- The only recipient is CALLMEBOT_TELEGRAM_USER from .env (a Telegram @username or +phone number). Nothing here takes
  a recipient from a caller, so a call can never reach anyone else.
- At most JARVIS_CALLS_PER_DAY calls a day (default 5), the same text at most once an hour: ONE count shared with the two-way
  Telegram calls (jarvis_tgcall.reserve/refund), saved across restarts, holding only a hash of the text.
- The text goes to CallMeBot's servers: callers keep it to a short alert (cut to MAX_TEXT_CHARS here).
Setup on the phone: in Telegram, open @CallMeBot_txtbot and press Start (or allow calls from it) once.
"""
from __future__ import annotations

import os
import re
import urllib.parse
import urllib.request

import jarvis_tgcall as _cap   # the daily cap + same-text rule live there, shared by both kinds of call

API_URL = "https://api.callmebot.com/start.php"
MAX_TEXT_CHARS = 250  # CallMeBot reads at most 256 characters


def user() -> str:
    """The owner's Telegram @username or +phone number, or "" when calls aren't set up."""
    value = (os.environ.get("CALLMEBOT_TELEGRAM_USER") or "").strip().strip('"').strip("'")
    if not value:
        return ""
    if re.fullmatch(r"\+?\d{7,15}", value.replace(" ", "")):
        value = value.replace(" ", "")
        return value if value.startswith("+") else "+" + value
    if re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,31}", value):
        return value if value.startswith("@") else "@" + value
    return ""


def configured() -> bool:
    return bool(user())


def per_day() -> int:
    return _cap.per_day()


def clean_text(text: str) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or ""))
    text = re.sub(r"https?://\S+", "a link", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS].rsplit(" ", 1)[0].rstrip(",;:") + "."
    return text


def build_url(to: str, text: str) -> str:
    params = {"user": to, "text": text}
    lang = (os.environ.get("CALLMEBOT_LANG") or "").strip()
    if lang:
        params["lang"] = lang
    repeat = (os.environ.get("CALLMEBOT_REPEAT") or "2").strip()
    params["rpt"] = str(max(1, min(5, int(repeat)))) if repeat.isdigit() else "2"
    return API_URL + "?" + urllib.parse.urlencode(params)


def _refusal(body: str) -> str | None:
    """CallMeBot answers with a short HTML page; known failure wording becomes a reason."""
    low = re.sub(r"<[^>]+>", " ", body or "").lower()
    for words, reason in (
        (("spam",),
         "CallMeBot's caller bot was reported as spam and is locked for new calls: in Telegram, find the bot that "
         "called you before in your call history (@CallMeBot_API or @CallMeBot_API<number>, e.g. @CallMeBot_API16), "
         "add it to your contacts and send it any message, then try again"),
        (("not authorized", "not authorised", "authorize", "authorise"),
         "CallMeBot isn't allowed to call you yet: open @CallMeBot_txtbot in Telegram and press Start"),
        (("not found", "invalid user", "unknown user", "username not"),
         "CallMeBot doesn't know that Telegram user (check CALLMEBOT_TELEGRAM_USER)"),
        (("too many",), "CallMeBot is limiting calls right now; try again later"),
        (("error",), "CallMeBot returned an error"),
    ):
        if any(w in low for w in words):
            return reason
    return None


def call(text: str, opener=None) -> tuple[bool, str]:
    """Rings the owner's Telegram and reads `text`. Returns (ok, what happened). Never raises."""
    to = user()
    if not to:
        return False, ("phone calls aren't set up: put your Telegram @username or phone number in "
                       "CALLMEBOT_TELEGRAM_USER (Settings), then press Start on @CallMeBot_txtbot in Telegram")
    text = clean_text(text)
    if not text:
        return False, "nothing to say on the call"
    why = _cap.reserve(text)
    if why:
        return False, why
    opener = opener or urllib.request.urlopen
    try:
        req = urllib.request.Request(build_url(to, text), headers={"User-Agent": "Jarvis"})
        with opener(req, timeout=30) as resp:
            body = resp.read(4000).decode("utf-8", "replace")
    except Exception as e:  # network trouble: the call didn't happen, so it doesn't count toward the cap
        _cap.refund(text)
        return False, f"couldn't reach CallMeBot ({type(e).__name__})"
    reason = _refusal(body)
    if reason:
        _cap.refund(text)
        return False, reason
    return True, "CallMeBot is ringing your Telegram"


def reset_for_tests() -> None:
    _cap.reset_for_tests()
