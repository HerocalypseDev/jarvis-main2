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
    """The task the child sees (Version A or B). No "Version A/B" label: the field it goes in says which."""
    base = hw["task_a"] if str(which).upper() == "A" else hw["task_b"]
    common = (hw.get("task_common") or "").strip()
    return f"{base} {common}".strip()


def question_specs(hw: dict) -> list[dict]:
    """The questions to add: the 6 multiple-choice (30 points, both versions) and one short answer per version (10 points)."""
    specs = [{"type": "mcq", "prompt": q["q"], "options": list(q["options"]), "correct_option": q["answer"],
              "points": MCQ_POINTS, "version": "both"} for q in hw["quiz"]]
    specs.append({"type": "short", "prompt": hw["short_a"], "points": SHORT_POINTS, "version": "A"})
    specs.append({"type": "short", "prompt": hw["short_b"], "points": SHORT_POINTS, "version": "B"})
    return specs


def spec_key(prompt, version) -> tuple[str, str]:
    return (_norm(prompt), str(version or "both"))


def missing_specs(hw: dict, existing: list[dict]) -> list[dict]:
    """Specs not already in the app's homework (matched on question text and version), so re-running never duplicates."""
    have = {spec_key(q.get("prompt"), q.get("version")) for q in existing or []}
    return [s for s in question_specs(hw) if spec_key(s["prompt"], s["version"]) not in have]


def format_homework(hw: dict) -> str:
    letters = "abc"
    lines = [f"{app_title(hw)} (week {hw['week']}), guide due date {hw['due_date']} {hw['due_time']}",
             f"Quiz ({hw.get('quiz_note') or 'same for both'}; 6 x {MCQ_POINTS} = 30 points):"]
    for i, q in enumerate(hw["quiz"], 1):
        opts = "  ".join(f"({letters[j]}) {o}{' [correct]' if j == q['answer'] else ''}" for j, o in enumerate(q["options"]))
        lines.append(f"{i}. {q['q']} {opts}")
    lines += [f"Short answer ({SHORT_POINTS} points): A: {hw['short_a']}", f"  B: {hw['short_b']}",
              f"Task (60 points): A: {task_text(hw, 'A')}", f"  B: {task_text(hw, 'B')}", hw["marking_notes"]]
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
