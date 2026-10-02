"""Jarvis4U Pro dashboard widgets: pure computations (no I/O, no Jarvis import).

A Pro pack describes widgets as data (`pro/widgets/*.json`, validated by `jarvis_pro.validate_widget`). Jarvis reads
the rows for each widget's `source` itself (read-only) and this module turns them into plain JSON the dashboard draws
with fixed code. Nothing from a pack is ever executed or inserted as HTML; text is escaped by the dashboard.

Fact lines follow the shared formats in PRO_ROADMAP.md, e.g.
    Exam: Chemistry on 2026-11-03 09:00
    Exam score: Physics 14/20 on 2026-10-02 (weak: projectile motion, units)
    Job application: Flutterwave / Junior QA / applied 2026-10-02 / status applied
"""
from __future__ import annotations

import re
from datetime import date, datetime

_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_SCORE_RE = re.compile(r"^(?P<subject>.+?)\s+(?P<n>\d+(?:\.\d+)?)\s*/\s*(?P<total>\d+(?:\.\d+)?)\b")
_WEAK_RE = re.compile(r"\(weak:\s*([^)]*)\)", re.I)
_NUM_RE = re.compile(r"\b(\d+)\b")
_BOARD_ORDER = ["idea", "planned", "applied", "interview", "offer", "posted", "done", "rejected", "withdrawn", "stopped"]
MAX_TEXT = 140


def _clip(text: str) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT - 1] + "…"


def strip_prefix(line: str, prefix: str) -> str:
    line = str(line or "").strip()
    return line[len(prefix):].strip() if prefix and line.startswith(prefix) else line


def _to_date(text: str) -> date | None:
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def _countdown(lines: list[str], prefix: str, today: date, limit: int) -> list[dict]:
    out = []
    for line in lines:
        body = strip_prefix(line, prefix)
        when = _to_date(body)
        if not when or when < today:
            continue
        label = re.split(r"\s+on\s+\d{4}-\d{2}-\d{2}", body, maxsplit=1)[0]
        label = _DATE_RE.sub("", label).strip(" /-,") or body
        out.append({"label": _clip(label), "date": when.isoformat(), "days": (when - today).days})
    seen, uniq = set(), []
    for item in sorted(out, key=lambda x: (x["days"], x["label"])):
        if (item["label"].lower(), item["date"]) not in seen:
            seen.add((item["label"].lower(), item["date"]))
            uniq.append(item)
    return uniq[:limit]


def _score_trend(lines: list[str], prefix: str, limit: int) -> list[dict]:
    per: dict[str, list[tuple[str, float, str]]] = {}
    names: dict[str, str] = {}
    for line in lines:
        body = strip_prefix(line, prefix)
        m = _SCORE_RE.match(body)
        if not m:
            continue
        try:
            total = float(m.group("total"))
            pct = round(100 * float(m.group("n")) / total) if total > 0 else None
        except ValueError:
            pct = None
        if pct is None or not 0 <= pct <= 100:
            continue
        when = _to_date(body)
        mw = _WEAK_RE.search(body)
        weak = mw.group(1) if mw else ""
        key = m.group("subject").strip().lower()
        names.setdefault(key, _clip(m.group("subject").strip()))
        per.setdefault(key, []).append((when.isoformat() if when else "", pct, weak.strip()))
    out = []
    for key, pts in per.items():
        pts.sort(key=lambda p: p[0])
        series = [p[1] for p in pts][-12:]
        out.append({"subject": names[key], "points": series, "latest": series[-1], "first": series[0],
                    "sessions": len(pts), "weak": _clip(pts[-1][2]), "last_date": pts[-1][0]})
    out.sort(key=lambda s: s["last_date"], reverse=True)
    return out[:limit]


def _board(lines: list[str], prefix: str, limit: int) -> list[dict]:
    columns: dict[str, list[str]] = {}
    seen = set()
    for line in lines:                       # newest first: the first line for an item wins
        parts = [p.strip() for p in strip_prefix(line, prefix).split(" / ") if p.strip()]
        if not parts:
            continue
        status = next((p[7:].strip().lower() for p in parts if p.lower().startswith("status ")), "other")
        label_parts = [p for p in parts if not p.lower().startswith(("status ", "applied ", "date "))
                       and not _DATE_RE.fullmatch(p)][:2]
        label = " · ".join(label_parts) or parts[0]
        if label.lower() in seen:
            continue
        seen.add(label.lower())
        columns.setdefault(_clip(status)[:20] or "other", []).append(_clip(label))
    order = [s for s in _BOARD_ORDER if s in columns] + sorted(s for s in columns if s not in _BOARD_ORDER)
    return [{"status": s, "items": columns[s][:limit], "count": len(columns[s])} for s in order]


def _stat(lines: list[str], prefix: str) -> dict:
    if not lines:
        return {"value": None, "caption": ""}
    newest = strip_prefix(lines[0], prefix)
    m = _NUM_RE.search(newest)
    return {"value": int(m.group(1)) if m else len(lines), "caption": _clip(newest)}


def compute(spec: dict, rows: list, today: date) -> dict:
    """One widget's data. `rows` depends on the source: facts -> list of fact lines (newest first);
    reminders -> list of (text, due_at); meetings -> list of (title, started_at, status)."""
    kind, source = spec["type"], spec["source"]
    prefix, limit = spec.get("prefix") or "", int(spec.get("limit") or 5)
    out = {"id": spec["id"], "title": spec["title"], "type": kind}
    if source == "reminders":
        lines = [f"{text} on {str(due)[:10]}" for text, due in rows]
        items = [{"label": _clip(text), "when": str(due)[:16].replace("T", " ")} for text, due in rows]
    elif source == "meetings":
        lines = [f"{title or 'Meeting'} on {str(started)[:10]}" for title, started, _status in rows]
        items = [{"label": _clip(title or "Meeting"), "when": str(started)[:16].replace("T", " ")}
                 for title, started, _status in rows]
    else:
        lines = [str(r) for r in rows]
        items = [{"label": _clip(strip_prefix(r, prefix)), "when": ""} for r in lines]
    if kind == "list":
        out["items"] = items[:limit]
    elif kind == "countdown":
        out["items"] = _countdown(lines, prefix if source == "facts" else "", today, limit)
    elif kind == "score_trend":
        out["subjects"] = _score_trend(lines, prefix, limit)
    elif kind == "board":
        out["columns"] = _board(lines, prefix, limit)
    elif kind == "stat":
        out.update(_stat(lines, prefix))
    out["empty"] = not any(out.get(k) for k in ("items", "subjects", "columns")) and out.get("value") is None
    return out
