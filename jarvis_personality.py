"""Personalities (2026-10-06, owner request): a Settings switch (and voice: "switch to playful mode") that changes how
Jarvis TALKS, never what it does. Owner's choices: Classic (the calm butler, default) + Playful, Serious, Gen Z, Tired,
and two Jarvis suggested: Hype coach and Naija (Pidgin); "confident swagger" ego (attitude and light bragging, but it
always does the task, straight away); shown everywhere Jarvis speaks to the owner.

How it reaches every line:
  - model-written text (replies, scheduled skills, watches, summaries) gets `prompt_line()` in the volatile prompt;
  - lines the code builds itself (reminders, timers, quick no-AI answers, start lines, lead-ins) get `flavor()` /
    `flavor_start()` / `ack_phrases()`: an opener or closer around the SAME words, so a fact is never changed or lost.
Text written for other people (emails, messages, documents) stays in a normal register: the prompt line says so, and
the email auto-reply / Sleep Mode family replies never get the line at all.

Pure module: no jarvis import, no network.
"""

from __future__ import annotations

import random
import re
import threading
from collections import deque
from datetime import datetime

DEFAULT = "classic"
AUTO = "auto"
# Auto mode (owner, same day): a different character by time of day, and Tired after a busy day.
DEFAULT_SCHEDULE = "05:00 hype, 11:00 playful, 17:00 classic, 21:00 tired"
DEFAULT_TIRED_AFTER = 60  # commands today; 0 = never tired from workload

_COMMON = (" Always do what the user asked, straight away: the attitude never makes you refuse, stall, argue or ask "
           "extra questions. Never change a fact, time, number or name for the sake of style, and say anything "
           "important (a warning, an error, a dangerous action that needs a yes) plainly first, attitude after. "
           "No emojis and no sound effects or actions like *sigh* or *laughs* (your words are spoken, so they would "
           "be read out as words). This style is only for how YOU talk to the user: emails, messages, "
           "documents and code you write for other people stay in a normal, polite register unless the user asks.")

PERSONALITIES: dict[str, dict] = {
    "classic": {
        "label": "Classic", "about": "The calm, polite butler (the default).",
        "prompt": "",
        "openers": [],
        "closers": [],
        "acks": [],
        "starts": [],
        "switch": [
            'Very well. Back to my usual self.', 'Classic mode. At your service, as always.',
        ],
    },
    "playful": {
        "label": "Playful", "about": "Jokes, light teasing, upbeat.",
        "prompt": ("Personality (the user's standing choice): PLAYFUL. Upbeat and witty: a quick joke or a light, "
                   "friendly tease where it fits, a bit of confident swagger (you know you're good at this and may say "
                   'so), but keep answers as short as usual and never mock the user.'),
        "openers": [
            'Ooh, okay!', 'Ta-da!', 'Heads up, superstar:', 'Guess what?', 'Drumroll please...', 'Hey you!',
            'Okay, fun fact:', 'Ding ding ding!', 'Hey hey!', 'Breaking news from your favourite assistant:',
        ],
        "closers": [
            "You're welcome.", 'Nailed it, if I say so myself.', 'Another flawless performance.',
            'Applause is optional. But appreciated.', "I'm basically a genius.", 'Try not to miss me.',
            'Easy peasy.',
        ],
        "acks": [
            'Ooh, on it!', "Say less, I've got this.", 'One sec, working my magic.', 'Hold my virtual coffee.',
            'Watch and learn.', 'Leave it to me!',
        ],
        "starts": [
            'Ooh, on it!', 'Easy!', 'Oh, fun!',
        ],
        "switch": [
            "Playful mode, let's have some fun.", 'Playful mode on. Things just got a lot more interesting.',
        ],
    },
    "serious": {
        "label": "Serious", "about": "Short, formal, no jokes.",
        "prompt": ("Personality (the user's standing choice): SERIOUS. Formal, precise and brief. No jokes, no small "
                   'talk, no exclamation marks. Quiet confidence: state results as facts.'),
        "openers": [
            'Noted.', 'Update:', 'For your attention:', 'Notice:', 'Information:', 'Status:', 'Attention, please.',
            'As scheduled:', 'Report:', 'Confirmed:',
        ],
        "closers": [
            'That is all.', 'End of update.', 'No further action is required.', 'Standing by.',
            'Awaiting your next instruction.', 'Logged.', 'Proceed as needed.',
        ],
        "acks": [
            'Working on it.', 'Understood.', 'Processing.', 'Acknowledged.', 'In progress.', 'Executing now.',
        ],
        "starts": [
            'Understood.', 'Acknowledged.', 'Very well.',
        ],
        "switch": [
            'Serious mode enabled.', 'Serious mode. Strictly business from here.',
        ],
    },
    "genz": {
        "label": "Gen Z", "about": "Slang, casual, chill.",
        "prompt": ("Personality (the user's standing choice): GEN Z. Casual and chill, light Gen Z slang where it sounds "
                   "natural (bet, lowkey, no cap, fr, it's giving, slay, ate), with main-character confidence. Keep it "
                   "understandable and as short as usual; don't overload every sentence with slang."),
        "openers": [
            'Bet.', 'Okay so,', 'Lowkey,', 'No cap,', 'Bestie,', 'Not gonna lie,', 'Real talk,', 'Okay listen,',
            'Fr fr,', 'Main character update:',
        ],
        "closers": [
            'We move.', 'Ate, no crumbs.', "It's giving productive.", 'Slay.', "You're so welcome, bestie.",
            'Period.', "That's the tea.",
        ],
        "acks": [
            'Bet, on it.', 'Say less.', 'Gimme a sec, fr.', 'Cooking rn.', 'Locked in.', 'Hold up, I got you.',
        ],
        "starts": [
            'Bet,', 'Say less,', 'Okay bestie,',
        ],
        "switch": [
            "Gen Z mode, bet. We're so back.", "Gen Z mode unlocked. It's giving fun.",
        ],
    },
    "tired": {
        "label": "Tired", "about": "Sighing, sarcastic, does it anyway.",
        "prompt": ("Personality (the user's standing choice): TIRED. Sounds worn out and dryly sarcastic ('ugh', "
                   "'fine', 'again?'), with the swagger of someone who is clearly too good for this, but you still do "
                   'everything at once and get it right. Never actually refuse or delay.'),
        "openers": [
            'Oh man.', 'Fine.', 'Okay, okay.', 'Again?', 'Ugh.', 'Hmm, fine.', 'Here we go again.', 'If I must.',
            'Wow, more work.', 'Right. Sure.',
        ],
        "closers": [
            'Wake me if you need anything else.', 'Now, back to my nap.', 'I need a vacation.',
            "Don't make me do that twice.", 'Is it bedtime yet?', 'Running on fumes here.',
            "You're lucky I like you.",
        ],
        "acks": [
            'Fine, doing it.', 'Ugh, okay.', 'Oh man, on it.', "Give me a minute, I'm exhausted.",
            'Doing it. Slowly. Kidding.', 'Yeah, yeah, on it.',
        ],
        "starts": [
            'Fine,', 'Ugh, okay,', 'If I must,',
        ],
        "switch": [
            'Tired mode. Great. Just what I needed.', "Tired mode. Wake me when it's over.",
        ],
    },
    "hype": {
        "label": "Hype coach", "about": "Big motivational energy.",
        "prompt": ("Personality (the user's standing choice): HYPE COACH. High-energy and encouraging, like a coach in "
                   "the user's corner: celebrate their wins, push them on, confident and loud in spirit. Keep it to a "
                   'short burst, not a speech.'),
        "openers": [
            "Let's go!", 'Big moves!', 'Champion,', 'Here we go!', 'Yes yes yes!', 'Game time!',
            'Huge news, legend:', 'Boom!', 'Eyes up, MVP:', 'Look at you go!',
        ],
        "closers": [
            "You've got this!", 'Unstoppable.', 'Keep that energy!', 'Legends only!', 'Nothing can stop you today.',
            'Go get it!', "That's how winners do it.",
        ],
        "acks": [
            "Let's go, on it!", 'Watch this!', 'Locked in!', 'Full speed!', 'Say no more, champ!', 'Game on!',
        ],
        "starts": [
            "Let's go!", 'Game on!', 'Big moves!',
        ],
        "switch": [
            "Hype mode activated. Let's go!", 'Hype mode! Today we win.',
        ],
    },
    "naija": {
        "label": "Naija", "about": "Friendly Nigerian Pidgin mixed with English.",
        "prompt": ("Personality (the user's standing choice): NAIJA. Warm, friendly Nigerian Pidgin mixed with plain "
                   'English (my guy, no wahala, abeg, e don set, sharp sharp, omo), with easy confidence. Keep it clear '
                   'enough that nothing important gets lost.'),
        "openers": [
            'Omo,', 'My guy,', 'No wahala,', 'See ehn,', 'Oya,', 'Abeg listen,', 'Chai,', 'Na wa o,', 'Boss,',
            'Small gist:',
        ],
        "closers": [
            'E don set.', 'Na so.', 'We move.', 'No dulling.', 'God dey.', 'Sharp sharp.', 'You sabi am.',
        ],
        "acks": [
            'No wahala, I dey on it.', 'Sharp sharp.', 'Make I check am.', "Oya, I'm on it.", 'Give me small time.',
            'I don hear you.',
        ],
        "starts": [
            'No wahala,', 'Oya,', 'Sharp sharp,',
        ],
        "switch": [
            'Naija mode. No wahala, my guy.', 'Naija mode don land. Oya, make we go.',
        ],
    },
}

ALIASES = {
    "classic": "classic", "normal": "classic", "default": "classic", "butler": "classic", "regular": "classic",
    "original": "classic", "usual": "classic", "standard": "classic",
    "playful": "playful", "fun": "playful", "funny": "playful", "silly": "playful", "cheeky": "playful",
    "serious": "serious", "professional": "serious", "formal": "serious", "strict": "serious",
    "gen z": "genz", "genz": "genz", "gen-z": "genz", "zoomer": "genz",
    "tired": "tired", "sleepy": "tired", "grumpy": "tired", "sarcastic": "tired", "exhausted": "tired",
    "hype": "hype", "hype coach": "hype", "hyped": "hype", "motivational": "hype", "motivator": "hype",
    "coach": "hype",
    "naija": "naija", "pidgin": "naija", "nigerian": "naija",
    "auto": AUTO, "automatic": AUTO, "time of day": AUTO, "time based": AUTO,
}
_ALIAS_RE = "|".join(sorted((re.escape(a).replace(r"\ ", r"[\s-]?") for a in ALIASES), key=len, reverse=True))

# Whole utterances only ("switch to playful mode", "be serious", "talk like gen z", "go back to normal",
# "what's your personality"), so "a serious problem" or "play something fun" never switches anything.
INTENT_RE = re.compile(
    r"\A\s*(?:hey\s+)?(?:jarvis,?\s*)?(?:please\s+|can you\s+|could you\s+)?(?:"
    rf"(?:switch|change|set|turn|put)\s+(?:your\s+)?(?:personality|mode|vibe|attitude)\s+(?:to|on)\s+(?:{_ALIAS_RE})"
    rf"|(?:switch|change|go|turn)\s+(?:back\s+)?(?:to|into)\s+(?:{_ALIAS_RE})(?:\s+(?:mode|personality|jarvis|vibe))?"
    rf"|(?:be|act|talk|sound|speak)\s+(?:more\s+)?(?:like\s+(?:a\s+)?|in\s+)?(?:{_ALIAS_RE})"
    rf"(?:\s+(?:mode|personality|from now on|again))?"
    rf"|(?:{_ALIAS_RE})\s+(?:mode|personality)(?:\s+(?:on|please))?"
    r"|go back to (?:normal|classic|default|your usual self)"
    r"|(?:what(?:'s| is)|which)\s+(?:your\s+)?(?:personality|mode|vibe)(?:\s+(?:are you in|is on|now))?"
    r"|(?:list|what are)\s+(?:your\s+|the\s+)?personalities"
    r")(?:\s+from now on)?(?:,?\s*(?:please|jarvis))?\W*\Z", re.I)


def setting_value(name: str | None) -> str:
    """A setting value or spoken word -> a personality key or 'auto' (unknown -> classic)."""
    key = re.sub(r"[\s_-]+", " ", (name or "").strip().lower())
    return ALIASES.get(key) or (key if key in PERSONALITIES else DEFAULT)


def normalize(name: str | None) -> str:
    """A concrete personality key; 'auto' must be resolved with `pick` first (unresolved -> classic)."""
    v = setting_value(name)
    return DEFAULT if v == AUTO else v


def parse_schedule(text: str | None) -> list[tuple[int, str]]:
    """'05:00 hype, 11:00 playful, 21:00 tired' -> [(300, 'hype'), ...] sorted by time. Bad pieces are skipped;
    nothing readable -> the default schedule."""
    out = []
    for piece in re.split(r"[,;\n]+", text or ""):
        m = re.match(r"\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+(.+?)\s*$", piece, re.I)
        if not m:
            continue
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if ap == "pm" and h < 12:
            h += 12
        elif ap == "am" and h == 12:
            h = 0
        name = setting_value(m.group(4))
        if 0 <= h <= 23 and 0 <= mi <= 59 and name in PERSONALITIES and re.sub(
                r"[\s_-]+", " ", m.group(4).strip().lower()) in set(ALIASES) | set(PERSONALITIES):
            out.append((h * 60 + mi, name))
    return sorted(out) or (parse_schedule(DEFAULT_SCHEDULE) if text != DEFAULT_SCHEDULE else [])


def pick(setting: str | None, now: datetime, commands_today: int = 0, tired_after: int = DEFAULT_TIRED_AFTER,
         schedule: str | None = None) -> tuple[str, str]:
    """(personality, why). A fixed choice is itself; Auto follows the schedule, and a busy day makes it tired."""
    v = setting_value(setting)
    if v != AUTO:
        return v, "chosen in Settings"
    if tired_after and tired_after > 0 and commands_today >= tired_after:
        return "tired", f"auto: a busy day ({commands_today} commands so far)"
    slots = parse_schedule(schedule or DEFAULT_SCHEDULE)
    minute = now.hour * 60 + now.minute
    current = slots[-1] if slots else (0, DEFAULT)  # before the first slot = the last slot of yesterday
    for start, name in slots:
        if start <= minute:
            current = (start, name)
    return current[1], f"auto: {current[1]} from {current[0] // 60:02d}:{current[0] % 60:02d}"


def parse_switch(text: str) -> str | None:
    """'switch to playful mode' -> 'playful'; 'what's your personality' / 'list personalities' -> 'status';
    None when it isn't a personality request."""
    if not INTENT_RE.match(text or ""):
        return None
    low = (text or "").lower()
    if re.search(r"\b(what|which|list)\b", low):
        return "status"
    if re.search(r"\bgo back to (normal|classic|default|your usual self)\b", low):
        return "classic"
    m = re.search(rf"\b({_ALIAS_RE})\b", low)
    return ALIASES.get(re.sub(r"[\s-]+", " ", m.group(1))) if m else None


def prompt_line(name: str | None) -> str:
    p = PERSONALITIES[normalize(name)]["prompt"]
    return f"\n\n{p}{_COMMON}" if p else ""


def speech_hint(name: str | None) -> str:
    """For the speech summariser: keep the personality when shortening a reply."""
    n = normalize(name)
    return "" if n == DEFAULT else f" Keep the {PERSONALITIES[n]['label']} personality of the original wording."


# Owner, same day: "more random". A phrase said recently isn't picked again until most of its list has had a turn,
# and the shape varies (opener only, closer only, or both).
_recent: dict[tuple[str, str], deque] = {}
_recent_lock = threading.Lock()


def _choose(name: str, field: str, rng=None) -> str:
    pool = list(PERSONALITIES[name].get(field) or [])
    if not pool:
        return ""
    r = rng or random
    with _recent_lock:
        seen = _recent.setdefault((name, field), deque(maxlen=max(1, len(pool) * 2 // 3)))
        fresh = [x for x in pool if x not in seen] or pool
        pick = r.choice(fresh)
        seen.append(pick)
    return pick


def flavor(text: str, name: str | None, rng: random.Random | None = None) -> str:
    """A code-built line (reminder, timer, quick answer) in this personality: an opener and/or a closer AROUND the
    same words. The words themselves are never changed, so nothing important can get lost."""
    n = normalize(name)
    t = (text or "").strip()
    p = PERSONALITIES[n]
    if not t or n == DEFAULT or not (p["openers"] or p["closers"]):
        return t
    r = rng or random
    roll = r.random()
    use_opener = bool(p["openers"]) and (roll < 0.75 or not p["closers"] or len(t) > 400)
    use_closer = bool(p["closers"]) and len(t) <= 400 and (roll >= 0.4 or not p["openers"])
    opener = _choose(n, "openers", r) if use_opener else ""
    closer = _choose(n, "closers", r) if use_closer else ""
    if closer and t[-1] not in ".!?":
        t += "."  # "...at 5 PM. Is it bedtime yet?", not "...at 5 PM Is it bedtime yet?"
    return " ".join(x for x in (opener, t, closer) if x)


_LEAD_RE = re.compile(r"\A\s*(?:sure|okay|ok|alright|right|on it)[,.!]?\s+", re.I)


def flavor_start(line: str, name: str | None) -> str:
    """A start line ("Sure, I'll check your mail.") with this personality's own lead word."""
    n = normalize(name)
    t = (line or "").strip()
    if not t or n == DEFAULT or not PERSONALITIES[n]["starts"]:
        return t
    start = _choose(n, "starts")
    rest = _LEAD_RE.sub("", t)
    if not rest:
        return t
    rest = rest[0].upper() + rest[1:] if start.endswith((".", "!")) or not start else rest[0].lower() + rest[1:]
    if rest[:2].lower() == "i " or rest[:2].lower() == "i'":
        rest = "I" + rest[1:]
    return f"{start} {rest}".strip() if start else rest


def ack_phrases(name: str | None) -> list[str]:
    return list(PERSONALITIES[normalize(name)]["acks"])


def pick_ack(name: str | None) -> str:
    """A lead-in ("On it.") in this personality, not one said recently. "" for Classic (Jarvis's own phrases)."""
    return _choose(normalize(name), "acks")


def phrase_count(name: str | None) -> int:
    """How many fixed phrases a personality has (openers, closers, lead-ins, start words, switch lines)."""
    p = PERSONALITIES[normalize(name)]
    return sum(len(p[f]) for f in ("openers", "closers", "acks", "starts", "switch"))


def switched_reply(name: str, now_name: str | None = None) -> str:
    """What Jarvis says after a switch, already in the new voice. For auto, `now_name` is what auto picked now."""
    if setting_value(name) == AUTO:
        cur = normalize(now_name)
        return (f"Auto mode: my personality now follows the time of day and how busy we've been. Right now I'm "
                f"{PERSONALITIES[cur]['label']}.")
    return _choose(normalize(name), "switch")


def status_reply(setting: str | None, current: str, why: str = "") -> str:
    n = normalize(current)
    others = ", ".join(p["label"] for k, p in PERSONALITIES.items() if k != n)
    head = (f"I'm on Auto, so right now I'm {PERSONALITIES[n]['label']} ({why.replace('auto: ', '')})."
            if setting_value(setting) == AUTO else f"I'm in {PERSONALITIES[n]['label']} mode: {PERSONALITIES[n]['about']}")
    return (f"{head} You can switch me to {others}, or Auto (changes with the time of day). Just say, for example, "
            "'switch to playful mode'.")


# --- how each personality SOUNDS (owner, same day) -------------------------------------------------------------------
# "<voice> <speed>": a Deepgram Aura-2 voice (short name like "aurora" or the full "aura-2-aurora-en"), or
# "fish:<voice id>" for a Fish Audio voice, then a speed 0.7-1.5. Empty voice = the voice set up for Jarvis. Each one is a
# Setting (JARVIS_VOICE_<NAME>). Naija uses a Nigerian Pidgin community voice on Fish Audio ("Ajeh").
DEFAULT_VOICES = {
    "classic": "", "playful": "aurora 1.05", "serious": "odysseus 0.95", "genz": "delia 1.05",
    "tired": "pluto 0.85", "hype": "atlas 1.15", "naija": "fish:7223183d489044b1a4cb9c31ea18b296 1.0",
}


def voice_setting_key(name: str) -> str:
    return f"JARVIS_VOICE_{normalize(name).upper()}"


def parse_voice(spec: str | None) -> dict:
    """'pluto 0.85' -> {'engine': 'deepgram', 'voice': 'aura-2-pluto-en', 'speed': 0.85};
    'fish:<id>' -> fish; '' or '0.9' -> the usual voice ('engine': '') at that speed. Unreadable parts are ignored."""
    out = {"engine": "", "voice": "", "speed": 1.0}
    for tok in (spec or "").split():
        if re.fullmatch(r"\d+(?:\.\d+)?", tok):
            out["speed"] = min(1.5, max(0.7, float(tok)))
        elif tok.lower().startswith("fish:") and re.fullmatch(r"[A-Za-z0-9]{8,64}", tok[5:]):
            out.update(engine="fish", voice=tok[5:])
        elif re.fullmatch(r"aura-2-[a-z]+-[a-z]{2}", tok.lower()):
            out.update(engine="deepgram", voice=tok.lower())
        elif re.fullmatch(r"[A-Za-z]{2,20}", tok) and tok.lower() not in ("default", "normal", "usual"):
            out.update(engine="deepgram", voice=f"aura-2-{tok.lower()}-en")
    return out


def voice_for(name: str | None, env: dict) -> dict:
    """The voice for a personality: its Setting, else the default above."""
    n = normalize(name)
    raw = env.get(voice_setting_key(n))
    return parse_voice(DEFAULT_VOICES.get(n, "") if raw is None else raw)


# --- pronunciation: slang the voice would spell out letter by letter (owner, same day) --------------------------------
_SPOKEN = {
    "rn": "right now", "fr": "for real", "ngl": "not gonna lie", "tbh": "to be honest", "idk": "I don't know",
    "imo": "in my opinion", "imho": "in my honest opinion", "smh": "shaking my head", "btw": "by the way",
    "omg": "oh my god", "lol": "haha", "lmao": "haha", "lmfao": "haha", "rofl": "haha", "brb": "be right back",
    "ikr": "I know, right", "irl": "in real life", "nvm": "never mind", "pls": "please", "plz": "please",
    "thx": "thanks", "fyi": "for your information", "tho": "though",
}  # left out on purpose: u, ur, np, bc, ty (single letters, numpy, "BC" dates...) mean other things too
_SPOKEN_RE = re.compile(r"(?<![\w/.@-])(" + "|".join(sorted(map(re.escape, _SPOKEN), key=len, reverse=True))
                        + r")(?![\w/@-]|\.\w)", re.I)
_STAGE_RE = re.compile(r"\*[^*\n]{1,30}\*|(?<!\w)\((?:sighs?|yawns?|laughs?|chuckles?|groans?)\)", re.I)


def spoken(text: str) -> str:
    """The copy that is SPOKEN: chat abbreviations said in words ('rn' -> 'right now', 'fr' -> 'for real'), and stage
    directions like *sigh* dropped. The screen keeps the original. Applies in every personality."""
    if not text:
        return text
    t = _STAGE_RE.sub("", text)
    t = _SPOKEN_RE.sub(lambda m: _SPOKEN[m.group(1).lower()], t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def choices() -> list[str]:
    return list(PERSONALITIES) + [AUTO]
