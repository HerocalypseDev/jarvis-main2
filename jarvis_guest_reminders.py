"""Reminders while an unrecognized person is at the computer (driven by the face poll).

When the face poll declares a stranger, Jarvis asks the owner on Telegram whether to disable
reminders while they are there, and the owner's yes/no reply steers a small state machine:

    NORMAL --stranger--> AWAITING_ANSWER --yes--> DISABLED --stranger leaves--> AWAITING_REENABLE
                              |no                    ^   |no (stay off)              |yes
                              v                      |   +---------------------------+--> NORMAL
                           ALLOWED --stranger leaves--> NORMAL
    (AWAITING_ANSWER --stranger leaves--> NORMAL: the question is stale)

While a state "holds" reminders (AWAITING_ANSWER, DISABLED, AWAITING_REENABLE) a due reminder is
not spoken and its Windows toast is not shown; it is queued and read out when they come back on.
In DISABLED / AWAITING_REENABLE each held reminder is also texted to the owner, so it is not
missed. Nothing is ever dropped.

This module knows nothing about faces, the confirmation gate or Windows: jarvis.py hands it a
send function (Telegram) and a release function (speak what was held). State is in memory only,
on purpose: after a restart reminders are back to normal rather than silently off forever.
"""

from __future__ import annotations

import logging
import re
import threading
import time

log = logging.getLogger("jarvis")

NORMAL = "normal"
AWAITING_ANSWER = "awaiting_answer"
ALLOWED = "allowed"  # the owner said "no": reminders speak normally for the rest of this visit
DISABLED = "disabled"
AWAITING_REENABLE = "awaiting_reenable"

QUESTION_COOLDOWN_S = 600.0  # one question per visit at most, and not more than every 10 minutes

ASK_TEXT = (
    "Someone I don't recognize is at your computer. "
    "Should I disable reminders while they're here? Reply yes or no."
)
REENABLE_TEXT = "They've left. Should I turn reminders back on? Reply yes or no."

_lock = threading.RLock()
_state = NORMAL
_last_question_at = 0.0
_send = None  # send_fn(text) -> bool
_release = None  # release_fn() -> None


def configure(send_fn, release_fn) -> None:
    global _send, _release
    _send, _release = send_fn, release_fn


def reset() -> None:
    global _state, _last_question_at
    with _lock:
        _state, _last_question_at = NORMAL, 0.0


def state() -> str:
    return _state


def holding_reminders() -> bool:
    """True while due reminders must be held (not spoken, no toast)."""
    return _state in (AWAITING_ANSWER, DISABLED, AWAITING_REENABLE)


def reminders_allowed() -> bool:
    """True after the owner said "no": reminders speak even with a stranger in view."""
    return _state == ALLOWED


def should_forward() -> bool:
    """True when each held reminder should also be texted to the owner."""
    return _state in (DISABLED, AWAITING_REENABLE)


def has_open_question() -> bool:
    return _state in (AWAITING_ANSWER, AWAITING_REENABLE)


def forward_reminder(text: str) -> None:
    """Text a held reminder to the owner's phone (best effort; it stays queued either way)."""
    if _send:
        body = text[len("Reminder: "):] if text.startswith("Reminder: ") else text
        try:
            _send(f"Held reminder: {body}")
        except Exception as e:
            log.warning("could not forward held reminder: %s", e)


# --- transitions ------------------------------------------------------------------------------
def on_stranger_arrived(now: float | None = None) -> None:
    global _state, _last_question_at
    now = time.time() if now is None else now
    with _lock:
        if _state in (DISABLED, AWAITING_REENABLE):
            _state = DISABLED  # they're back before the owner turned reminders on: stay off
            return
        if _state in (AWAITING_ANSWER, ALLOWED) or now - _last_question_at < QUESTION_COOLDOWN_S:
            return
        if _send is None:
            return
    sent = False
    try:
        sent = bool(_send(ASK_TEXT))
    except Exception as e:
        log.warning("could not ask about reminders: %s", e)
    with _lock:
        if sent and _state == NORMAL:
            _state, _last_question_at = AWAITING_ANSWER, now
        elif not sent:
            log.info("Stranger seen but no phone channel to ask about reminders; using the default hold.")


def on_stranger_left() -> None:
    global _state
    ask = False
    with _lock:
        if _state in (AWAITING_ANSWER, ALLOWED):
            _state = NORMAL
        elif _state == DISABLED:
            _state, ask = AWAITING_REENABLE, True
    if ask:
        try:
            if _send:
                _send(REENABLE_TEXT)
        except Exception as e:
            log.warning("could not ask about re-enabling reminders: %s", e)


# --- the owner's reply ------------------------------------------------------------------------
_YES = {
    "yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "yes please", "please do", "go ahead",
    "do it", "affirmative", "sure thing", "please", "yes do it", "yes disable them", "yes turn them on",
}
_NO = {
    "no", "n", "nope", "nah", "no thanks", "no thank you", "dont", "don't", "do not", "not now",
    "negative", "no dont", "no don't",
}
# Context-specific phrasings (the same words mean opposite things depending on the question).
_YES_ASK = {"disable", "disable them", "disable reminders", "turn them off", "turn reminders off"}
_NO_ASK = {"keep them on", "leave them on", "keep reminders on", "leave reminders on", "keep them"}
_YES_REENABLE = {"enable", "enable them", "enable reminders", "turn them on", "turn them back on",
                 "turn reminders on", "turn reminders back on", "back on"}
_NO_REENABLE = {"keep them off", "leave them off", "keep reminders off", "leave reminders off", "stay off"}


def _norm(text: str) -> str:
    t = (text or "").strip().lower()
    if t in ("\U0001F44D",):  # thumbs up
        return "yes"
    if t in ("\U0001F44E",):
        return "no"
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]", " ", t)).strip()


def parse_yes_no(text: str, st: str | None = None) -> bool | None:
    """True/False for a clear yes/no, None otherwise. Deliberately strict: the WHOLE message must
    be a yes/no phrase ("yes", "no thanks", "keep them on"); "yes but what about ..." or "no
    problem" are not answers, so they fall through to normal command handling."""
    t = _norm(text)
    st = st or _state
    yes, no = set(_YES), set(_NO)
    if st == AWAITING_ANSWER:
        yes |= _YES_ASK
        no |= _NO_ASK
    elif st == AWAITING_REENABLE:
        yes |= _YES_REENABLE
        no |= _NO_REENABLE
    if t in yes:
        return True
    if t in no:
        return False
    return None


def answer(text: str) -> str | None:
    """Handle a reply to an open question. Returns the reply to send back, or None if there is no
    open question or the text is not a clear yes/no (so it is handled as an ordinary command)."""
    global _state
    release = False
    with _lock:
        if not has_open_question():
            return None
        verdict = parse_yes_no(text)
        if verdict is None:
            return None
        if _state == AWAITING_ANSWER:
            if verdict:
                _state = DISABLED
                reply = "Okay, reminders are off while they're here. I'll hold them and text you each one."
            else:
                _state, release = ALLOWED, True
                reply = "Okay, reminders stay on."
        else:  # AWAITING_REENABLE
            if verdict:
                _state, release = NORMAL, True
                reply = "Reminders are back on. Reading you the ones I held."
            else:
                _state = DISABLED
                reply = "Okay, reminders stay off. Say 'enable reminders' when you want them back."
    if release and _release:
        try:
            _release()
        except Exception as e:
            log.warning("could not release held reminders: %s", e)
    return reply


# --- explicit control (tool: voice, dashboard, phone) --------------------------------------------
def set_disabled(disabled: bool) -> str:
    global _state
    release = False
    with _lock:
        if disabled:
            _state = DISABLED
            reply = "Reminders are off. I'll hold them and text you each one until you turn them back on."
        else:
            release = holding_reminders()
            _state = NORMAL
            reply = "Reminders are on." + (" Reading you the ones I held." if release else "")
    if release and _release:
        try:
            _release()
        except Exception as e:
            log.warning("could not release held reminders: %s", e)
    return reply


def status() -> str:
    return {
        NORMAL: "Reminders are on.",
        ALLOWED: "Reminders are on (you chose to keep them while the visitor is here).",
        AWAITING_ANSWER: "Reminders are being held while I wait for your answer about the visitor.",
        DISABLED: "Reminders are off; I'm holding them and texting you each one.",
        AWAITING_REENABLE: "Reminders are still off; I'm waiting to hear whether to turn them back on.",
    }[_state]
