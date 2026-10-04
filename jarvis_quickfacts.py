"""Learning facts from what the owner says, at once (2026-10-03, owner: "learn from what I say").

Facts used to be picked up only by the autonomy session summary, 20+ idle minutes later (and only with autonomy on).
This reads clear statements about the owner as soon as they are said, locally, with no model call:
"my exam score was 280", "I live in Paris", "call me Sam", "my favourite anime is One Piece", "I'm a student at
the city college", "I scored 280 in my entrance exam", "I love jollof rice".

Deliberately narrow: only first-person statements, never questions, commands, hypotheticals or anything that looks
like a passing state ("my head is hurting", "my phone is dead"). Pure module (no jarvis import).
"""
from __future__ import annotations

import re

MAX_FACTS = 3
MAX_VALUE_WORDS = 14

# "my <thing> is/was <value>": only things that stay true (a passing state is not worth remembering).
_DURABLE = (
    "name|full name|surname|nickname|birthday|date of birth|age|school|university|uni|college|course|department|faculty|"
    "major|class|level|job|work|occupation|profession|company|boss|teacher|best friend|friend|brother|sister|mum|mom|"
    "mother|dad|father|wife|husband|girlfriend|boyfriend|son|daughter|uncle|aunt|cousin|grandma|grandpa|pastor|church|"
    "city|town|state|country|hometown|address|area|street|team|club|religion|blood group|genotype|height|weight|"
    "phone number|username|gamertag|laptop|phone|car|pc|exam number|registration number|reg number|"
    "cgpa|gpa|result|results|score|mark|marks|grade|grades"
)
_MY_RE = re.compile(
    r"\bmy (?P<subj>(?:favou?rite [a-z' ]{2,30}?|(?:[a-z]+'s )?(?:[a-z]+ ){0,3}?(?:" + _DURABLE + r")))"
    r"(?:'s| is| was| are| were)\s+(?P<val>[^.!?;]{1,120})", re.I)
_I_AM_RE = re.compile(r"\bi(?: am|'m) (?P<val>(?:a|an) (?!bit\b|little\b|lot\b|fan of you\b)[^.!?;,]{3,80}"
                      r"|\d{1,2} years? old|from [^.!?;,]{2,60}|studying [^.!?;,]{2,60}"
                      r"|in (?:ss ?[1-3]|jss ?[1-3]|year \d|\d{3} level|primary \d)[^.!?;,]{0,40})", re.I)
_LIVE_RE = re.compile(r"\bi (?:live|stay|reside) in (?P<val>[^.!?;,]{2,60})", re.I)
_WORK_RE = re.compile(r"\bi (?P<verb>work|study|school) (?:at|in|for) (?P<val>[^.!?;,]{2,60})", re.I)
_LIKE_RE = re.compile(r"\bi (?:really |do |also )?(?P<verb>like|love|enjoy|prefer|hate|dislike|can't stand|cannot stand"
                      r"|don't like|do not like) (?P<val>[^.!?;,]{2,60})", re.I)
_CALL_RE = re.compile(r"\bcall me (?P<val>[a-z][a-z' -]{1,30})", re.I)
_SCORED_RE = re.compile(r"\bi (?:scored|got|had) (?P<num>\d[\d./%]*(?: (?:points|marks|percent))?) in (?:my |the )?"
                        r"(?P<subj>[^.!?;,]{2,40})", re.I)
_BORN_RE = re.compile(r"\bi was born (?P<val>(?:on|in) [^.!?;]{2,40})", re.I)

# Never learned, whatever the wording: secrets and money details (they would sit in every prompt and could reach an
# auto-reply to someone the owner knows).
_SENSITIVE_RE = re.compile(r"\b(?:password|passcode|pass ?word|pin|cvv|card|account|bank|bvn|nin|ssn|otp|code|secret|"
                           r"token|key|api|login|sort code|iban|routing|"
                           # audit 2026-10-04: a phone number or home address learned silently sat in every prompt
                           # and could reach a known sender's automatic email reply; say "remember ..." to keep them
                           r"phone number|mobile number|phone no|address|passport)\b", re.I)
_QUESTION_RE = re.compile(r"^\s*(?:what|when|where|who|whom|whose|why|how|which|is|are|was|were|do|does|did|can|could|"
                          r"would|will|should|shall|have|has|am)\b", re.I)
_SKIP_RE = re.compile(r"\b(?:if|suppose|imagine|pretend|what if|wish|hope|maybe|probably|might|tell (?:him|her|them)|"
                      r"he said|she said|they said|reply|write|draft|email|message|type|send|say)\b", re.I)
_VAGUE_VAL_RE = re.compile(r"^(?:it|that|this|those|them|these|you|your|yours|him|her|when|how|what|so|too|very|not)\b",
                           re.I)
_TRANSIENT_VAL_RE = re.compile(r"\b(?:dead|broken|slow|hurting|aching|low|charging|off|tired|sick|ill|busy|"
                               r"bored|hungry|late|now|today|tomorrow|tonight|right now|currently|at the moment|"
                               r"hospital|angry|annoyed|annoying|upset|mad|sad|away|travell?ing|on (?:his|her|their|the) way)\b|%",
                               re.I)
# "my brother is annoying" / "my mum is in the hospital" are opinions or passing states, not who someone is: a person's
# value must be a name ("Ada") or a role ("a doctor", "the head of ...") (audit 2026-10-04).
_PERSON_VAL_RE = re.compile(r"^(?:[A-Z]|(?:a|an|the) [a-z])")
# "call me later / back / when you're free / a taxi" is not a name (audit 2026-10-04).
_CALL_NOT_NAME_RE = re.compile(r"^(?:later|back|tomorrow|soon|now|when|whenever|if|at|in|on|after|before|tonight|again|"
                               r"please|anytime|asap|once|first|today|maybe|then|by|around|sometime|next|this|a|an|the|"
                               r"up|out|over|immediately|quickly|in a bit)\b", re.I)
# "I live in fear of exams" is an idiom, not a place.
_LIVE_IDIOM_RE = re.compile(r"^(?:fear|hope|denial|peace|harmony|the past|a dream|a bubble|my head|misery|shame)\b", re.I)
_FAMILY_RE = re.compile(r"\b(?:friend|brother|sister|mum|mom|mother|dad|father|wife|husband|girlfriend|boyfriend|son|"
                        r"daughter|uncle|aunt|cousin|grandma|grandpa|pastor|boss|teacher)\b")


def _clean(v: str) -> str:
    v = re.sub(r"\s+", " ", v).strip(" ,'\"-")
    v = re.sub(r"\s+(?:and|but|so|because|which|though)\b.*$", "", v, flags=re.I)  # one fact, not the whole sentence
    return v.strip(" ,'\"-")


def _key(*parts: str) -> str:
    return "auto:" + re.sub(r"[^a-z0-9]+", "_", " ".join(parts).lower()).strip("_")[:40]


def _ok_value(v: str) -> bool:
    return bool(v) and len(v.split()) <= MAX_VALUE_WORDS and not _VAGUE_VAL_RE.match(v) and \
        not re.search(r"@|https?://|www\.", v)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n+", text or "") if s.strip()]


def extract(text: str) -> list[dict]:
    """[{category, key, content}] from the owner's own words. Empty for questions, commands and hypotheticals."""
    out: list[dict] = []
    for s in _sentences(text):
        low = s.lower().strip()
        if s.rstrip().endswith("?") or _QUESTION_RE.match(low) or _SKIP_RE.search(low):
            continue
        if re.match(r"^\s*(?:hey,?\s*)?(?:jarvis,?\s*)?(?:remember|note|don't forget|do not forget|save|forget)\b", low):
            continue  # an explicit "remember that..." goes through remember_fact; don't store it twice
        for m in _MY_RE.finditer(s):
            subj, val = _clean(m.group("subj")).lower(), _clean(m.group("val"))
            if _SENSITIVE_RE.search(m.group(0)):
                continue
            verb = "is" if m.group(0).lower().split(subj, 1)[-1].strip().startswith(("is", "'s")) else \
                m.group(0).lower().split(subj, 1)[-1].split()[0]
            if not _ok_value(val) or _TRANSIENT_VAL_RE.search(val):
                continue
            if _FAMILY_RE.search(subj) and not _PERSON_VAL_RE.match(val):
                continue
            out.append({"category": "preference" if subj.startswith("favo") else
                        "relationship" if _FAMILY_RE.search(subj) else "fact",
                        "key": _key("my", subj), "content": f"The user's {subj} {verb} {val}."})
        for m in _I_AM_RE.finditer(s):
            val = _clean(m.group("val"))
            if _ok_value(val) and not _TRANSIENT_VAL_RE.search(val):
                key = (_key("age") if re.search(r"years? old", val) else _key("from") if val.lower().startswith("from")
                       else _key("user is", *val.split()[:2]))
                out.append({"category": "fact", "key": key, "content": f"The user is {val}."})
        for rx, label, key in ((_LIVE_RE, "lives in", "lives_in"), (_BORN_RE, "was born", "born")):
            m = rx.search(s)
            if m and _ok_value(_clean(m.group("val"))) and not _LIVE_IDIOM_RE.match(_clean(m.group("val"))):
                out.append({"category": "fact", "key": _key(key), "content": f"The user {label} {_clean(m.group('val'))}."})
        m = _WORK_RE.search(s)
        if m and _ok_value(_clean(m.group("val"))):
            verb = {"work": "works", "study": "studies", "school": "schools"}[m.group("verb").lower()]
            prep = re.search(r"\b(at|in|for)\b", m.group(0)[len("i ") + len(m.group("verb")):], re.I).group(1).lower()
            out.append({"category": "fact", "key": _key(verb), "content": f"The user {verb} {prep} {_clean(m.group('val'))}."})
        m = _LIKE_RE.search(s)
        if m:
            val = _clean(m.group("val"))
            if _ok_value(val) and not re.search(r"\b(?:you|your|when|how|it when|that)\b", val, re.I) and \
                    not re.match(r"^(?:to|it)\b", val, re.I):
                verb = m.group("verb").lower().replace("can't stand", "can't stand").replace("cannot stand", "can't stand")
                verb = {"like": "likes", "love": "loves", "enjoy": "enjoys", "prefer": "prefers", "hate": "hates",
                        "dislike": "dislikes", "don't like": "doesn't like", "do not like": "doesn't like"}.get(verb, verb)
                out.append({"category": "preference", "key": None, "content": f"The user {verb} {val}."})
        m = _CALL_RE.search(s)
        if m and _ok_value(_clean(m.group("val"))) and not _CALL_NOT_NAME_RE.match(_clean(m.group("val"))):
            out.append({"category": "preference", "key": _key("call me"),
                        "content": f"The user wants to be called {_clean(m.group('val'))}."})
        m = _SCORED_RE.search(s)
        if m and _ok_value(_clean(m.group("subj"))):
            subj = _clean(m.group("subj"))
            out.append({"category": "fact", "key": _key("score", subj),
                        "content": f"The user scored {m.group('num')} in their {subj}."})
    seen, uniq = set(), []
    for f in out:
        if f["content"].lower() not in seen:
            seen.add(f["content"].lower())
            uniq.append(f)
    return uniq[:MAX_FACTS]
