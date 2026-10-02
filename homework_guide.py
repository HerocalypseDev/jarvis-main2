"""The Teacher's Guide as data: the 8 homeworks (quiz, short answers, tasks, marking notes) and the 4 lessons.

`homework_curriculum.json` was extracted from the owner's "Introduction to AI - Teacher's Guide" PDF. The MCP server
(homework_mcp_server.py) uses this module so that "add the questions to the homework" copies the guide exactly instead of
the model retyping (and dropping) questions. Pure functions, no network, never imports jarvis.py. Private, like every
homework_* file (kept out of the public export).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "homework_curriculum.json"
MCQ_POINTS = 5
SHORT_POINTS = 10


@lru_cache(maxsize=1)
def _load() -> dict:
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"homeworks": [], "lessons": []}


def homeworks() -> list[dict]:
    return list(_load().get("homeworks") or [])


def lessons() -> list[dict]:
    return list(_load().get("lessons") or [])


def get(number) -> dict | None:
    try:
        n = int(number)
    except (TypeError, ValueError):
        return None
    return next((h for h in homeworks() if h.get("number") == n), None)


def lesson(week) -> dict | None:
    try:
        w = int(week)
    except (TypeError, ValueError):
        return None
    return next((x for x in lessons() if x.get("week") == w), None)


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower()).strip()


def find_for_title(title: str, week=None) -> dict | None:
    """Which guide homework an app homework is: by "Homework N" in its title, else by the guide's own title words
    (so "AI audit" or "Week 2 prompt portfolio" are found). None when nothing or more than one matches."""
    t = _norm(title)
    m = re.search(r"\bhomework\s*(\d+)\b", t)
    if m:
        return get(m.group(1))
    hits = [h for h in homeworks() if _norm(h["title"]) in t]
    if week is not None:
        by_week = [h for h in hits if str(h.get("week")) == str(week)]
        hits = by_week or hits
    return hits[0] if len(hits) == 1 else None


def app_title(hw: dict) -> str:
    return f"Homework {hw['number']} - {hw['title']}"


def task_text(hw: dict, which: str) -> str:
    """The task the child sees (Version A or B), exactly as the guide words it. No "Version A/B" label: the field it goes in says which."""
    return hw["task"][str(which).upper()].strip()


def marking_notes(hw: dict) -> str:
    """Private notes for the teacher/marker: the marking guide plus what a good short answer looks like for each student.
    (The guide's answer key is "for you only; don't paste it", so it lives here and never in anything the child reads.)"""
    return (f"{hw['marking_guide']} Short answer, what a good one looks like (teacher only): "
            f"younger student (James): {hw['short_key']['A']} older student (Peter): {hw['short_key']['B']}")


def _mcq_spec(q: dict, version: str) -> dict:
    return {"type": "mcq", "prompt": q["q"], "options": list(q["options"]), "correct_option": q["answer"],
            "points": MCQ_POINTS, "version": version}


def question_specs(hw: dict) -> list[dict]:
    """The questions to add: the 6 multiple-choice (30 points) and the short answer (10 points) for each version. The guide
    gives each version in full; where both versions are word for word the same one question is added for both."""
    quiz_a, quiz_b = hw["quiz"]["A"], hw["quiz"]["B"]
    if quiz_a == quiz_b:
        specs = [_mcq_spec(q, "both") for q in quiz_a]
    else:
        specs = [_mcq_spec(q, "A") for q in quiz_a] + [_mcq_spec(q, "B") for q in quiz_b]
    short_a, short_b = hw["short"]["A"], hw["short"]["B"]
    if short_a == short_b:
        specs.append({"type": "short", "prompt": short_a, "points": SHORT_POINTS, "version": "both"})
    else:
        specs.append({"type": "short", "prompt": short_a, "points": SHORT_POINTS, "version": "A"})
        specs.append({"type": "short", "prompt": short_b, "points": SHORT_POINTS, "version": "B"})
    return specs


def _same_prompt(spec: dict, q: dict) -> bool:
    return _norm(q.get("prompt")) == _norm(spec["prompt"])


def matches(spec: dict, existing: list[dict]) -> list[dict]:
    """The questions already in the app that cover this spec (same text; a "both" question covers A and B; for a "both"
    spec the app may hold the A and B copies instead)."""
    same = [q for q in existing or [] if _same_prompt(spec, q)]
    if spec["version"] == "both":
        both = [q for q in same if str(q.get("version") or "both") == "both"]
        if both:
            return both
        a = [q for q in same if q.get("version") == "A"]
        b = [q for q in same if q.get("version") == "B"]
        return a + b if a and b else []
    return [q for q in same if str(q.get("version") or "both") in (spec["version"], "both")]


def missing_specs(hw: dict, existing: list[dict]) -> list[dict]:
    """Specs not already in the app's homework, so re-running never duplicates."""
    return [s for s in question_specs(hw) if not matches(s, existing)]


def differences(hw: dict, existing: list[dict]) -> list[tuple[dict, dict]]:
    """(app question, spec) pairs where a multiple-choice question is in the app but its options or correct answer differ
    from the guide (e.g. made from an older edition of the guide)."""
    out = []
    for spec in question_specs(hw):
        if spec["type"] != "mcq":
            continue
        for q in matches(spec, existing):
            opts = [_norm(o) for o in q.get("options") or []]
            if opts != [_norm(o) for o in spec["options"]] or q.get("correct_option") != spec["correct_option"]:
                out.append((q, spec))
    return out


def format_homework(hw: dict) -> str:
    letters = "abc"
    lines = [f"{app_title(hw)} (week {hw['week']}), guide due date {hw['due_date']} {hw['due_time']}"]
    for v, who in (("A", "younger student, James"), ("B", "older student, Peter")):
        lines.append(f"Version {v} ({who}) - multiple choice (6 x {MCQ_POINTS} = 30 points):")
        for i, q in enumerate(hw["quiz"][v], 1):
            opts = "  ".join(f"({letters[j]}) {o}{' [correct]' if j == q['answer'] else ''}" for j, o in enumerate(q["options"]))
            lines.append(f"{i}. {q['q']} {opts}")
        lines.append(f"Short answer ({SHORT_POINTS} points): {hw['short'][v]}")
        lines.append(f"Task (60 points): {task_text(hw, v)}")
    lines.append(marking_notes(hw))
    return "\n".join(lines)


def format_overview() -> str:
    data = _load()
    lines = [data.get("scoring", ""), data.get("versions", "")]
    for h in homeworks():
        lines.append(f"Homework {h['number']}: {h['title']} (week {h['week']}, due {h['due_date']} {h['due_time']})")
    return "\n".join(x for x in lines if x)


def format_lesson(lsn: dict) -> str:
    lines = [f"Week {lsn['week']} lesson, Sunday {lsn['sunday']}: {lsn['title']}", f"Goal: {lsn['goal']}",
             f"Key terms: {lsn['key_terms']}", "Theory:"]
    lines += [f"- {t}" for t in lsn["theory"]]
    lines.append(f"Practical: {lsn['practical']}")
    return "\n".join(lines)
