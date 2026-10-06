"""Watches (2026-10-06, owner request): "keep monitoring something I name (my timetable, my calendar...) and when
something important comes up - by the rule I give when I set it up - say it out loud and tell me".

A watch = what to check + the user's own rule for "important" + a schedule. Each due check is one unattended agent
run (jarvis.py) that answers with JSON alerts; this module decides, in code, what is NEW: each item is said once per
stage (owner's choice): first notice, 2 weeks, 3 days, tomorrow, today, and once just after it passed.
Owner's choices: its own feature (not a skill), schedule per watch (default daily 08:00), spoken right away but
held in Sleep/Focus/Safe mode like the owner's own reminders.

Pure module: no jarvis import, no network. The DB connect function and lock come from jarvis.py.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

DEFAULT_SCHEDULE = {"daily_at": "08:00"}
MIN_EVERY_MINUTES = 15          # each check is a model call: never a per-minute burn of the daily allowance
CATCH_UP_HOURS = 6              # same rule as daily skills: a PC switched on late doesn't run the 8 am check at 11 pm
RETRY_AFTER_MIN = 30            # a check whose model call failed is retried, at most RETRY_MAX times
RETRY_MAX = 2
MAX_WATCHES = 30
MAX_ALERTS = 6
PAST_GRACE_DAYS = 2             # "the results came out yesterday" is still worth saying once; older is stale
TOLD_KEEP_DAYS = 180
MAX_TEXT = 1200
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# --- schedule ------------------------------------------------------------------------------------------------------
_NAMED_TIMES = {"morning": "08:00", "noon": "12:00", "midday": "12:00", "afternoon": "14:00", "evening": "18:00",
                "night": "20:00", "tonight": "20:00"}
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?(?=\W|$)", re.I)
_DAY_WORDS = {"monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu", "friday": "fri",
              "saturday": "sat", "sunday": "sun", "mon": "mon", "tue": "tue", "tues": "tue", "wed": "wed",
              "thu": "thu", "thur": "thu", "thurs": "thu", "fri": "fri", "sat": "sat", "sun": "sun"}


def _hhmm(h: int, m: int) -> str | None:
    return f"{h:02d}:{m:02d}" if 0 <= h <= 23 and 0 <= m <= 59 else None


def _cron(text: str) -> dict | None:
    """'0 8 * * *', '30 7 * * 1-5', '0 */3 * * *' -> a schedule dict (the common shapes only)."""
    parts = text.split()
    if len(parts) != 5 or parts[2] != "*" or parts[3] != "*":
        return None
    minute, hour, dow = parts[0], parts[1], parts[4]
    out: dict = {}
    m = re.fullmatch(r"\*/(\d{1,3})", hour)
    if m and minute.isdigit():
        out["every_minutes"] = int(m.group(1)) * 60
    elif hour == "*" and re.fullmatch(r"\*/(\d{1,4})", minute):
        out["every_minutes"] = int(minute[2:])
    elif hour.isdigit() and minute.isdigit():
        t = _hhmm(int(hour), int(minute))
        if not t:
            return None
        out["daily_at"] = t
    else:
        return None
    if dow != "*":
        days = []
        for piece in dow.split(","):
            r = re.fullmatch(r"(\d)(?:-(\d))?", piece)
            if not r:
                return None
            a, b = int(r.group(1)), int(r.group(2) or r.group(1))
            days += [_WEEKDAYS[(d - 1) % 7] for d in range(a, b + 1)]  # cron 0/7 = Sunday, 1 = Monday
        out["days"] = ",".join(dict.fromkeys(days))
    return out


def parse_schedule(value) -> tuple[dict | None, str]:
    """Anything a model or the user may say about timing -> (schedule dict, note). (None, why) when unreadable.
    Accepts a dict (daily_at / every_minutes / days), cron strings and plain words ("every day at 8",
    "every 3 hours", "weekdays at 7:30 pm", "every morning", "hourly")."""
    if value in (None, "", {}):
        return dict(DEFAULT_SCHEDULE), "every day at 08:00 (the default)"
    if isinstance(value, dict):
        out = {}
        if value.get("daily_at"):
            m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(value["daily_at"]).strip())
            t = m and _hhmm(int(m.group(1)), int(m.group(2)))
            if not t:
                return None, f"I couldn't read the time {value['daily_at']!r}"
            out["daily_at"] = t
        elif value.get("every_minutes") not in (None, ""):
            try:
                out["every_minutes"] = float(value["every_minutes"])
            except (TypeError, ValueError):
                return None, f"I couldn't read every_minutes={value['every_minutes']!r}"
        else:
            return None, "the schedule needs daily_at (HH:MM) or every_minutes"
        if value.get("days"):
            days = [_DAY_WORDS.get(d.strip().lower()) for d in str(value["days"]).split(",") if d.strip()]
            if not days or None in days:
                return None, f"I couldn't read the days {value['days']!r}"
            out["days"] = ",".join(days)
        return _floor(out)
    text = re.sub(r"\s+", " ", str(value)).strip().lower()
    if re.fullmatch(r"[\d*/,\-]+( [\d*/,\-]+){4}", text):
        cron = _cron(text)
        return _floor(cron) if cron else (None, f"I couldn't read the timing {value!r}")
    out = {}
    m = re.search(r"\bevery (\d+|a|an|one|two|three|four|six|twelve)?\s*(minute|min|hour|hr)s?\b", text)
    if re.search(r"\bhourly\b", text):
        out["every_minutes"] = 60
    elif m:
        n = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "six": 6, "twelve": 12}.get(
            m.group(1) or "a", None)
        n = n if n is not None else int(m.group(1))
        out["every_minutes"] = n * (60 if m.group(2).startswith("h") else 1)
    else:
        t = None
        tm = _TIME_RE.search(text.replace("o'clock", ""))
        if tm and (tm.group(2) or tm.group(3) or re.search(r"\bat\s+" + re.escape(tm.group(0).strip()), text)):
            h, mi = int(tm.group(1)), int(tm.group(2) or 0)
            ap = (tm.group(3) or "").replace(".", "")
            if ap == "pm" and h < 12:
                h += 12
            elif ap == "am" and h == 12:
                h = 0
            t = _hhmm(h, mi)
            if not t:
                return None, f"I couldn't read the time in {value!r}"
        if not t:
            for word, hhmm in _NAMED_TIMES.items():
                if re.search(rf"\b{word}\b", text):
                    t = hhmm
                    break
        if not t and not re.search(r"\b(daily|every ?day|each day|once a day|weekdays?|weekends?|"
                                   r"mondays?|tuesdays?|wednesdays?|thursdays?|fridays?|saturdays?|sundays?)\b", text):
            return None, f"I couldn't read the timing {value!r}"
        out["daily_at"] = t or DEFAULT_SCHEDULE["daily_at"]
    if re.search(r"\bweekdays?\b", text):
        out["days"] = "mon,tue,wed,thu,fri"
    elif re.search(r"\bweekends?\b", text):
        out["days"] = "sat,sun"
    else:
        days = [v for k, v in _DAY_WORDS.items() if len(k) > 4 and re.search(rf"\b{k}s?\b", text)]
        if days:
            out["days"] = ",".join(dict.fromkeys(days))
    return _floor(out)


def _floor(out: dict) -> tuple[dict, str]:
    if "every_minutes" in out:
        n = out["every_minutes"]
        if not n or n < MIN_EVERY_MINUTES:
            out["every_minutes"] = MIN_EVERY_MINUTES
            return out, describe(out) + f" (the shortest gap is {MIN_EVERY_MINUTES} minutes: each check is an AI call)"
        out["every_minutes"] = int(n) if float(n).is_integer() else n
    return out, describe(out)


def describe(schedule: dict | None) -> str:
    s = schedule or {}
    days = s.get("days")
    when = f" on {days.replace(',', ', ')}" if days else ""
    if s.get("daily_at"):
        return f"every day at {s['daily_at']}" if not days else f"at {s['daily_at']}{when}"
    n = s.get("every_minutes")
    if n:
        n = float(n)
        gap = (f"{int(n // 60)} hours" if n % 60 == 0 and n > 60 else "hour" if n == 60 else f"{int(n)} minutes")
        return f"every {gap}{when}"
    return "only when asked"


def is_due(watch: dict, now: datetime) -> bool:
    if not watch.get("enabled"):
        return False
    s = watch.get("schedule") or {}
    if s.get("days") and _WEEKDAYS[now.weekday()] not in {d.strip()[:3] for d in str(s["days"]).split(",")}:
        return False
    last = _dt(watch.get("last_run"))
    fails = int(watch.get("fails") or 0)
    if last and 0 < fails <= RETRY_MAX and now - last >= timedelta(minutes=RETRY_AFTER_MIN):
        return True  # the model call failed last time: try again rather than miss a day
    if s.get("daily_at"):
        try:
            h, m = (int(p) for p in str(s["daily_at"]).split(":", 1))
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        except (TypeError, ValueError):
            return False
        if now < target or now - target > timedelta(hours=CATCH_UP_HOURS):
            return False
        return last is None or last < target
    if s.get("every_minutes"):
        try:
            gap = timedelta(minutes=max(float(s["every_minutes"]), MIN_EVERY_MINUTES))
        except (TypeError, ValueError):
            return False
        return last is None or now - last >= gap
    return False


def _dt(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


# --- stages + "already told" ----------------------------------------------------------------------------------------
def stage_for(event: date | None, today: date) -> str | None:
    """Which stage an item is at. None = too old to mention."""
    if event is None:
        return "now"
    days = (event - today).days
    if days < -PAST_GRACE_DAYS:
        return None
    if days < 0:
        return "passed"
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days <= 3:
        return "3 days"
    if days <= 14:
        return "2 weeks"
    return "ahead"


_STOP = set("""a an the my your our of for to in on at and or is are be will with from by about this that it its
his her their up out soon coming next new date day time due""".split())


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower().replace("-", " ")) if w not in _STOP}


def same_item(a: str, a_date: str | None, b: str, b_date: str | None) -> bool:
    """Is a newly reported item the one told before? The model rewords names between checks ("Post-UTME exam" /
    "Post UTME examination"), so it is matched by shared words; two different dates make it a different item."""
    if a_date and b_date and abs((_d(a_date) - _d(b_date)).days) > 1:
        return False
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return (a or "").strip().lower() == (b or "").strip().lower()
    shared = len(wa & wb)
    return shared / min(len(wa), len(wb)) >= 0.6 or bool(shared >= 1 and a_date and a_date == b_date)


def _d(value) -> date:
    return date.fromisoformat(str(value)[:10])


def parse_date(value) -> date | None:
    s = str(value or "").strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_alerts(reply: str) -> list[dict] | None:
    """The check's JSON answer -> [{item, date, say}]. None when there's no readable JSON at all."""
    text = reply or ""
    dec = json.JSONDecoder()
    for m in re.finditer(r"[{\[]", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        alerts = obj.get("alerts") if isinstance(obj, dict) else obj if isinstance(obj, list) else None
        if not isinstance(alerts, list):
            continue
        out = []
        for a in alerts[:MAX_ALERTS * 2]:
            if not isinstance(a, dict):
                continue
            say = re.sub(r"\s+", " ", str(a.get("say") or "")).strip()[:400]
            item = re.sub(r"\s+", " ", str(a.get("item") or "")).strip()[:120] or say[:60]
            if say:
                d = parse_date(a.get("date"))
                out.append({"item": item, "date": d.isoformat() if d else "", "say": say})
        return out
    return None


def pick_new(alerts: list[dict], told: list[dict], today: date, *, repeat: bool = False) -> list[dict]:
    """The alerts worth saying now: each item once per stage (an item seen first at "3 days" is never also said at
    "2 weeks"), stale past items dropped. With repeat=True (the user asked for a check right now) everything current
    is said again."""
    out = []
    for a in alerts:
        stage = stage_for(parse_date(a.get("date")), today)
        if stage is None:
            continue
        earlier = [t for t in told if same_item(a["item"], a.get("date") or None, t["item"], t.get("event_date") or None)]
        if not repeat and any(t["stage"] == stage for t in earlier):
            continue
        if not repeat and stage == "ahead" and earlier:
            continue
        if any(same_item(a["item"], a.get("date") or None, o["item"], o.get("date") or None) for o in out):
            continue  # the model listed the same thing twice
        out.append(dict(a, stage=stage))
        if len(out) >= MAX_ALERTS:
            break
    return out


# --- the check's prompt ---------------------------------------------------------------------------------------------
def check_prompt(watch: dict, told: list[dict], now: datetime, user_name: str = "", *, manual: bool = False) -> str:
    told_lines = "\n".join(
        f"- {t['item']}" + (f" ({t['event_date']})" if t.get("event_date") else "") + f": told at stage '{t['stage']}'"
        f" on {str(t['told_at'])[:10]}" for t in told[-25:]) or "- nothing yet"
    who = user_name or "the user"
    return (
        f"(This is {'a check the user just asked for' if manual else 'a scheduled check'} of the user's watch "
        f"\"{watch['name']}\". Nothing you write is read out as it is: only your JSON alerts are.)\n"
        f"What to check: {watch['what']}\n"
        f"What counts as important (the user's own rule, from when they set this up): {watch['rule']}\n"
        + (f"What the user wants to hear when something matches: {watch['announce']}\n" if watch.get("announce") else "")
        + 
        f"Today is {now:%A %d %B %Y}, {now:%H:%M}.\n"
        f"Already told {who} (the code won't repeat these at the same stage, so don't worry about repeats):\n"
        f"{told_lines}\n"
        "Use your tools to actually look (read the file, calendar, page or mail the 'what to check' names). Never invent "
        "a date or an event: list only what you really read. Then reply with ONLY a JSON object, nothing else:\n"
        '{"alerts": [{"item": "a short name that stays the same between checks, e.g. Post-UTME exam", '
        '"date": "YYYY-MM-DD of the event, or empty if it has no date", '
        f'"say": "what to tell {who} out loud: one or two short, warm sentences'
        f'{", starting with their name" if user_name else ""}"}}]}}\n'
        "Include only things that match the user's rule, plus anything matching it that is coming up later (the code "
        "decides when to say each one: about two weeks, three days, the day before and on the day). When it "
        "fits, end 'say' with a short caring question, e.g. 'How are you feeling about it?'. "
        'If nothing matches, reply {"alerts": []}.')


# --- is the watch complete enough to run? (owner, 2026-10-06: "if not enough is given, ask me again") -------------
# Where to look: a file/folder, the calendar, mail, a web page, an app... A watch that doesn't say where can't check.
_SOURCE_RE = re.compile(
    r"(?:[a-z]:\\|[\\/]|\.(?:pdf|docx?|xlsx?|csv|txt|pptx?|json|md)\b|https?://|www\.|\b[a-z0-9-]+\.(?:com|org|net|"
    r"edu|ng|io|gov|ac)\b|\b(?:calendar|gmail|e-?mails?|mail|inbox|messages?|whatsapp|telegram|files?|folder|"
    r"documents?|downloads|desktop|pdf|spreadsheet|sheet|website|web ?site|page|portal|site|url|link|feed|news|"
    r"reminders?|memory|facts?|repo(?:sitory)?|github|weather|prices?|stock|crypto|"
    r"bitcoin|youtube|twitter|x\.com|channel)\b)", re.I)
_VAGUE_RULE_RE = re.compile(
    r"^\W*(?:any(?:thing)?|every ?thing|stuff|things?|important(?: (?:stuff|things?|ones?))?|anything "
    r"(?:important|new|interesting)|whatever(?: matters)?|you know|idk|if needed|when needed|important stuff)\W*$",
    re.I)


def _real_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]{2,}", text or "")


def missing_parts(name: str, what: str, rule: str, schedule_given, announce: str) -> list[str]:
    """What the user still has to say before a watch can be made, as questions to ask them. [] = complete.
    Deliberately strict: a vague watch would check the wrong thing or speak up about nothing, every day."""
    asks = []
    if not (name or "").strip():
        asks.append("What should this watch be called (a short name, e.g. 'exam timetable')?")
    if len(_real_words(what)) < 2:
        asks.append("What exactly should I keep checking?")
    elif not _SOURCE_RE.search(what):
        asks.append(f"Where should I look for '{clip(what, 80)}': a file (its name or folder), your Google Calendar, "
                    "your email, or a website (its address)?")
    if len(_real_words(rule)) < 2 or _VAGUE_RULE_RE.match(rule or ""):
        asks.append("What counts as important enough to tell you out loud (e.g. 'exam dates, results release, "
                    "resumption')?")
    if len(_real_words(announce)) < 2:
        asks.append("When something matches, what should I say (e.g. 'how many days are left, and ask how I feel')?")
    if not schedule_given:
        asks.append("How often should I check (e.g. every day at 8 am, which is the usual, or every 3 hours)?")
    return asks


def clip(text, n: int = MAX_TEXT) -> str:
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", str(text or "")).strip()[:n]


# --- storage ----------------------------------------------------------------------------------------------------------
class Store:
    def __init__(self, connect, lock):
        self._connect, self._lock = connect, lock

    def _conn(self):
        conn = self._connect()
        conn.row_factory = _dict_row
        if True:  # cheap; the DB path can differ between runs (tests use a temp DB)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS watches (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE "
                "COLLATE NOCASE, what TEXT NOT NULL, rule TEXT NOT NULL, schedule TEXT NOT NULL, enabled INTEGER NOT "
                "NULL DEFAULT 1, start_line TEXT, created_at TEXT NOT NULL, last_run TEXT, last_status TEXT, "
                "last_result TEXT, fails INTEGER NOT NULL DEFAULT 0, announce TEXT)")
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(watches)")}
            if "announce" not in cols:
                conn.execute("ALTER TABLE watches ADD COLUMN announce TEXT")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS watch_told (id INTEGER PRIMARY KEY AUTOINCREMENT, watch_id INTEGER NOT "
                "NULL, item TEXT NOT NULL, event_date TEXT, stage TEXT NOT NULL, said TEXT, told_at TEXT NOT NULL)")
        return conn

    def _q(self, sql: str, args=(), write: bool = False):
        with self._lock:
            conn = self._conn()
            try:
                cur = conn.execute(sql, args)
                if write:
                    conn.commit()
                    return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount
                return cur.fetchall()
            finally:
                conn.close()

    @staticmethod
    def _load(row: dict) -> dict:
        try:
            row["schedule"] = json.loads(row.get("schedule") or "{}")
        except ValueError:
            row["schedule"] = {}
        return row

    def all(self) -> list[dict]:
        return [self._load(r) for r in self._q("SELECT * FROM watches ORDER BY id")]

    def get(self, watch_id: int) -> dict | None:
        rows = self._q("SELECT * FROM watches WHERE id = ?", (watch_id,))
        return self._load(rows[0]) if rows else None

    def find(self, name: str) -> tuple[dict | None, str]:
        """By id, exact name, or words from the name/what ("timetable", "my exam watch")."""
        name = (name or "").strip()
        watches = self.all()
        if not name:
            if len(watches) == 1:
                return watches[0], ""
            return None, "say which watch (its name)"
        if name.isdigit() or name.startswith("#") and name[1:].isdigit():
            hit = next((w for w in watches if w["id"] == int(name.lstrip("#"))), None)
            return (hit, "") if hit else (None, f"no watch #{name.lstrip('#')}")
        exact = [w for w in watches if w["name"].lower() == name.lower()]
        if exact:
            return exact[0], ""
        want = _words(name) - {"watch", "watches", "monitor", "monitoring", "check", "tracker"}
        scored = sorted(((len(want & (_words(w["name"].replace("_", " ")) | _words(w["what"]))), w) for w in watches),
                        key=lambda p: -p[0])
        if not scored or scored[0][0] == 0:
            return None, f"no watch matches {name!r}"
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            return None, ("more than one watch matches: " + ", ".join(w["name"] for s, w in scored if s == scored[0][0]))
        return scored[0][1], ""

    def create(self, name: str, what: str, rule: str, schedule: dict, start_line: str = "", announce: str = "") -> int:
        return self._q("INSERT INTO watches (name, what, rule, schedule, enabled, start_line, created_at, announce) "
                       "VALUES (?, ?, ?, ?, 1, ?, ?, ?)", (name, what, rule, json.dumps(schedule), start_line or None,
                                                         datetime.now().isoformat(timespec="seconds"), announce or None),
                       write=True)

    def similar(self, what: str, rule: str = "") -> dict | None:
        """An existing watch that already looks at the same thing (most of its words), so a second one isn't made."""
        want = _words(what) - {"check", "watch", "monitor", "keep", "eye"}
        for w in self.all():
            have = _words(w["what"])
            if want and have and len(want & have) / min(len(want), len(have)) >= 0.6:
                return w
        return None

    def update(self, watch_id: int, **fields) -> None:
        allowed = {"name", "what", "rule", "schedule", "enabled", "start_line", "last_run", "last_status",
                   "last_result", "fails", "announce"}
        fields = {k: (json.dumps(v) if k == "schedule" else v) for k, v in fields.items() if k in allowed}
        if fields:
            self._q(f"UPDATE watches SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                    (*fields.values(), watch_id), write=True)

    def delete(self, watch_id: int) -> None:
        self._q("DELETE FROM watch_told WHERE watch_id = ?", (watch_id,), write=True)
        self._q("DELETE FROM watches WHERE id = ?", (watch_id,), write=True)

    def told(self, watch_id: int) -> list[dict]:
        return self._q("SELECT item, event_date, stage, said, told_at FROM watch_told WHERE watch_id = ? ORDER BY id",
                       (watch_id,))

    def mark_told(self, watch_id: int, alert: dict) -> None:
        now = datetime.now()
        self._q("INSERT INTO watch_told (watch_id, item, event_date, stage, said, told_at) VALUES (?, ?, ?, ?, ?, ?)",
                (watch_id, alert["item"], alert.get("date") or None, alert["stage"], alert["say"],
                 now.isoformat(timespec="seconds")), write=True)
        self._q("DELETE FROM watch_told WHERE told_at < ?",
                ((now - timedelta(days=TOLD_KEEP_DAYS)).isoformat(timespec="seconds"),), write=True)


def _dict_row(cursor, row):
    return {d[0]: row[i] for i, d in enumerate(cursor.description)}
