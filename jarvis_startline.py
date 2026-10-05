"""Start lines (2026-10-05, owner request): the moment Jarvis starts a skill, a scheduled job, a routine or a
one-off task, it says one short sentence about THAT task ("Sure, I'll check the git status of your project.")
instead of a generic "On it." / "Sure, I'll run that on your PC now."

Owner's choices: a skill/job/routine gets its line written once when it is made (stored with it, spoken
instantly with no model call); when none was stored, one is built here from its own text; a one-off command's
line is built here from the user's own words. Pure module: no jarvis import, no model, no network.
"""

from __future__ import annotations

import re

MAX_CHARS = 140          # a stored line (written by the model when the skill/job/routine was made)
REQUEST_MAX_CHARS = 90   # a line built from the user's words: longer ones read like an echo, not an answer

_LEAD = re.compile(
    r"^\s*(?:(?:hey|hi|ok|okay|so|um|uh|yo)[,.! ]+)*(?:jarvis[,.! ]+)?(?:please[, ]+)?"
    r"(?:(?:can|could|would|will) you (?:please |kindly |just )?|i (?:need|want|would like) you to |"
    r"go (?:ahead )?and |i'd like you to |help me (?:to )?)?(?:please[, ]+)?", re.I)
# Verbs a task starts with (the same family as the spoken lead-in's task check in jarvis.py).
_VERB = re.compile(
    r"^(?:open|launch|start|search|find|look up|look for|check|send|email|write|create|make|set|set up|remind|"
    r"schedule|book|play|download|summari[sz]e|draft|add|show|read|list|fetch|get|save|copy|move|rename|"
    r"translate|research|plan|organi[sz]e|calculate|convert|call|text|message|fix|install|update|run|test|"
    r"measure|scan|review|compare|explain|tell|give|pull|push|build|clean up|sort|mark|grade|prepare|"
    r"go through|look at|watch|monitor|track|count|upload|post|reply to|answer|note|record|turn on|turn off|"
    r"switch|pause|resume|restart|provide|refresh|tidy|back up)\b", re.I)
# Never promise these before the confirmation gate has had its say: the generic lead-in stays for them.
_DANGEROUS = re.compile(
    r"\b(?:shut ?down|power off|reboot|format|wipe|erase|delete|remove|uninstall|kill|terminate|destroy|"
    r"log ?off|sign out|restart (?:my|the|this|your) (?:pc|computer|laptop|machine|system))\b", re.I)
_SWAP = {
    "my": "your", "me": "you", "mine": "yours", "myself": "yourself", "i": "you", "i'm": "you're", "im": "you're",
    "i've": "you've", "i'll": "you'll", "i'd": "you'd", "our": "your", "ours": "yours", "us": "you",
    "your": "my", "yours": "mine", "yourself": "myself",
}
_SWAP_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, _SWAP), key=len, reverse=True)) + r")\b", re.I)
_CUT_AT = re.compile(r",| and then | then | so that | because | which | after that | if ", re.I)
_TRAIL = re.compile(r"(?:[\s,]+(?:please|thanks|thank you|now please|for me please|asap|right now))+\s*$", re.I)


def clean(line) -> str:
    """A stored or built line made safe to speak: one sentence-ish line, no control characters, capped."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(line or ""))
    text = re.sub(r"\s+", " ", text).strip().strip("\"'")
    if not text:
        return ""
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rsplit(" ", 1)[0].rstrip(",;:") + "."
    if text[-1] not in ".!?":
        text += "."
    return text


def _swap_people(text: str) -> str | None:
    """'my project' -> 'your project'; None when a plain 'you' (could be I or me) makes the sentence ambiguous."""
    if re.search(r"\byou(?:'re|'ve|'ll)?\b", text, re.I):
        return None

    def sub(m: re.Match) -> str:
        word = m.group(1)
        out = _SWAP[word.lower()]
        return out[0].upper() + out[1:] if word[0].isupper() and word.lower() != "i" else out
    return _SWAP_RE.sub(sub, text)


def from_request(transcript: str) -> str | None:
    """'can you check the git status of my project' -> "Sure, I'll check the git status of your project."
    None when the words aren't a plain task (a question, chat, something dangerous, too long): the caller then
    keeps its generic lead-in."""
    raw = str(transcript or "")
    if not raw.strip() or "\n" in raw or "[" in raw or "<<<" in raw or len(raw) > 240:
        return None
    text = _LEAD.sub("", raw.strip(), count=1)
    text = re.sub(r"[.!?]+\s*$", "", text).strip()
    text = _TRAIL.sub("", text).strip()
    if not text or "?" in text or not _VERB.match(text) or _DANGEROUS.search(text):
        return None
    swapped = _swap_people(text)
    if not swapped:
        return None
    if len(swapped) > REQUEST_MAX_CHARS:
        m = _CUT_AT.search(swapped, 12)
        if not m or m.start() > REQUEST_MAX_CHARS:
            return None
        swapped = swapped[:m.start()].strip()
    swapped = swapped[0].lower() + swapped[1:]
    return clean(f"Sure, I'll {swapped}")


def from_text(text: str, name: str = "") -> str:
    """A line for a skill/job/routine that has none stored, from its own description/instruction. Always
    returns something (falls back to naming it)."""
    first = re.split(r"(?<=[.!?])\s|\n", str(text or "").strip(), maxsplit=1)[0]
    # descriptions often start "Runs automatically every hour to check ..." / "Use this when ..."
    first = re.sub(r"^(?:runs?|run) (?:automatically )?(?:every \w+|at [\d:]+\w*|daily|hourly|on [^,]+?)?\s*(?:to )?",
                   "", first, flags=re.I)
    first = re.sub(r"\b(?:automatically|every day|each day|daily|every hour|hourly)\b(?: at [\d:]+ ?(?:am|pm)?)?",
                   "", first, flags=re.I)
    first = re.sub(r"\s+", " ", first).strip(" ,;:")
    line = from_request(first)
    if line:
        return line
    label = re.sub(r"[_\-]+", " ", str(name or "")).strip()
    return clean(f"Starting {label}" if label else "Starting that now")
