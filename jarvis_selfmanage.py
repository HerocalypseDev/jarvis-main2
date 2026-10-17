"""Helpers for the `settings` and `stop_background_task` tools (2026-10-16): Jarvis changing what the owner can change
on the Settings / Tasks pages. Pure: no import of jarvis.py; jarvis.py hands in the settings listing.

The model may only set a setting that is on the curated Settings list, is not secret and is not in AI_DENIED. A
setting outside that (any other `.env` key, a secret, an executable path, a URL, the camera, meeting recording) is
read-only to it: the owner changes it on the Settings page.
"""
from __future__ import annotations

import re

# On the curated list but still the owner's own click: each either points Jarvis at a program/address/folder of the
# user's choosing, or switches on recording/camera, or is handled by a tool with its own rules (safe mode, personality).
AI_DENIED = {
    "JARVIS_RG_PATH": "it names a program Jarvis would run",
    "JARVIS_CODE_ROOTS": "it decides which folders Jarvis searches",
    "JARVIS_EVERYTHING_URL": "it is an address Jarvis sends queries to",
    "JARVIS_OLLAMA_URL": "it is an address Jarvis sends prompts to",
    "JARVIS_BROWSER_BRIDGE_PORT": "it opens a network port",
    "JARVIS_FACE_ENABLED": "it turns the camera on",
    "JARVIS_MEETING_AUTO": "it starts recording meetings by itself",
    "CALLMEBOT_TELEGRAM_USER": "it decides who Jarvis phones",
    "JARVIS_CALLS_PER_DAY": "it decides how often Jarvis may ring the owner",
    "TGCALL_API_ID": "it names the account Jarvis phones from",
    "TGCALL_API_HASH_SECRET": "it names the account Jarvis phones from",
    "TGCALL_TARGET": "it decides who Jarvis phones",
    "JARVIS_TGCALL_MAX_MIN": "it decides how long a phone call may run",
    "JARVIS_TGCALL_IDLE_S": "it decides how long a phone call may run",
    "JARVIS_TGCALL_DIR": "it decides where the phone login is stored",
}
# Handled by the tool that already has the right rules for them.
ROUTED = {"JARVIS_SAFE_MODE": "safe_mode", "JARVIS_PERSONALITY": "personality"}

_WORD = re.compile(r"[a-z0-9]+")
_FILLER = {"the", "a", "an", "my", "to", "of", "on", "off", "turn", "set", "change", "setting", "settings", "jarvis"}


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower().replace("_", " ")) if w not in _FILLER and len(w) > 1}


def rows(listing: dict) -> list[dict]:
    """Curated settings first, then the other .env keys (read-only)."""
    return list(listing.get("known") or []) + [dict(r, other=True) for r in listing.get("other") or []]


def find(listing: dict, query: str) -> list[dict]:
    """Settings matching `query`: an exact key wins; else every query word must appear in key/label/help."""
    q = (query or "").strip()
    if not q:
        return []
    exact = [r for r in rows(listing) if r["key"].lower() == q.lower().replace(" ", "_")]
    if exact:
        return exact
    want = _words(q)
    if not want:
        return []
    scored = []
    for r in rows(listing):
        head = _words(r["key"] + " " + str(r.get("label") or ""))
        body = head | _words(str(r.get("help") or ""))
        if want <= body:
            scored.append((len(want & head), r))
    scored.sort(key=lambda t: -t[0])
    if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return [scored[0][1]]
    return [r for _, r in scored][:8]


def show(row: dict) -> str:
    key = row["key"]
    if row.get("secret") or _is_secret_key(key):
        val = "(set)" if row.get("set", bool(row.get("value"))) else "(not set)"
    else:
        val = row.get("value")
        val = "(empty)" if val in (None, "") else str(val)[:120]
    label = f" - {row['label']}" if row.get("label") else ""
    extra = ""
    if row.get("choices"):
        extra = f" [choices: {', '.join(row['choices'])}]"
    elif row.get("kind") == "bool":
        extra = " [on/off]"
    where = "" if row.get("other") else f" (applies {row.get('applies', 'after restart')})"
    return f"{key}{label}: {val}{extra}{where}"


def _is_secret_key(key: str) -> bool:
    return bool(re.search(r"KEY|TOKEN|SECRET|PASSWORD|PASSCODE|PIN\b|_PIN|CREDENTIAL|COOKIE|TOPIC|CHAT_ID", key, re.I)) \
        and not key.endswith(("_KEY_NAME",)) and key not in ("JARVIS_PTT_KEY", "JARVIS_TEXT_HOTKEY_KEY",
                                                              "JARVIS_SELECTION_KEY", "JARVIS_APPSHOT_KEY",
                                                              "JARVIS_DICTATION_KEY")


def set_problem(row: dict | None) -> str | None:
    """Why the model may not set this one (None = it may). `row` is None for a key that isn't a known setting."""
    if row is None:
        return "that isn't a setting; the owner changes things like it on the Settings page"
    key = row["key"]
    if row.get("secret") or _is_secret_key(key):
        return "it is a secret (key, token, topic or chat id); the owner types it on the Settings page"
    if row.get("other"):
        return "that isn't one of the settings Jarvis may change itself; the owner changes it on the Settings page"
    if key in AI_DENIED:
        return f"{AI_DENIED[key]}; the owner changes it on the Settings page"
    return None


def listing_text(listing: dict, query: str = "", limit: int = 25) -> str:
    found = find(listing, query) if query else [r for r in rows(listing) if not r.get("other")]
    if query and not found:
        return f"No setting matches {query!r}. Ask with fewer words, or leave the query empty to list the settings."
    more = max(0, len(found) - limit)
    text = "\n".join(show(r) for r in found[:limit])
    return text + (f"\n(and {more} more: narrow it with words from the name)" if more else "")
