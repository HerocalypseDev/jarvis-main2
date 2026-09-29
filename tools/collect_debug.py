"""Collect what Jarvis did in the last few hours into one text file you can send for debugging.

    python tools/collect_debug.py              # last 3 hours
    python tools/collect_debug.py --hours 6

Writes debug_report.txt next to jarvis.py with, in time order:
  - every command (voice/typed/dashboard/phone) and Jarvis's full reply   (dashboard_sessions)
  - every tool call: its name, input (what was typed / clicked) and result (action_audit)
  - the Jarvis log lines from the same window                              (jarvis_standalone*.log)

Read-only: it never changes the database or the logs. Secrets are masked before anything is written: the value
of every secret-looking setting in .env (KEY/TOKEN/SECRET/PASSWORD/PIN/TOPIC/CHAT_ID), plus anything shaped like
an API key or token. Email addresses are shortened to their first letter + domain. Open the file and read it
before sending it to anyone; delete anything you'd rather keep private.
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET_NAME_RE = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|PIN\b|_PIN|TOPIC|CHAT_ID|COOKIE|CREDENTIAL", re.I)
KEY_SHAPES = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\bAQ\.[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bJ4U1\.[A-Za-z0-9_\-.]{20,}"),
    re.compile(r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}\b"),            # Telegram bot token
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}", re.I),
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),                        # long hex secrets
]
EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]*@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")
LOG_TIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def _env_secret_values() -> list[str]:
    out = []
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            name, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if SECRET_NAME_RE.search(name) and len(value) >= 4:
                out.append(value)
    return sorted(set(out), key=len, reverse=True)


def make_scrubber(secret_values: list[str]):
    def scrub(text: str) -> str:
        text = str(text or "")
        for v in secret_values:
            text = text.replace(v, "[SECRET]")
        for rx in KEY_SHAPES:
            text = rx.sub("[SECRET]", text)
        return EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text)
    return scrub


def _db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    return Path(override) if override else ROOT / "jarvis_memory.db"


def _rows(db: Path, since: str) -> list[tuple[str, str]]:
    """(timestamp, text block) for sessions and tool calls since `since`."""
    out: list[tuple[str, str]] = []
    if not db.exists():
        return [(since, f"(no database at {db})")]
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    try:
        try:
            for ts, src, tr, status, reply, end in conn.execute(
                    "SELECT started_at, source, transcript, status, reply, ended_at FROM dashboard_sessions "
                    "WHERE started_at >= ? ORDER BY started_at", (since,)):
                out.append((ts, f"=== COMMAND ({src}, {status}, ended {end or '-'})\n  said: {tr}\n"
                                f"  reply: {reply or ''}"))
        except sqlite3.Error as exc:
            out.append((since, f"(couldn't read dashboard_sessions: {exc})"))
        try:
            for ts, tool, inp, res, tr in conn.execute(
                    "SELECT timestamp, tool_name, tool_input, result, transcript FROM action_audit "
                    "WHERE timestamp >= ? ORDER BY timestamp, id", (since,)):
                out.append((ts, f"--- TOOL {tool}\n  for: {(tr or '')[:120]}\n  input: {inp}\n  result: {res}"))
        except sqlite3.Error as exc:
            out.append((since, f"(couldn't read action_audit: {exc})"))
    finally:
        conn.close()
    return out


def _log_lines(since_dt: datetime) -> list[tuple[str, str]]:
    out = []
    for name in ("jarvis_standalone.old.log", "jarvis_standalone.log"):
        p = ROOT / name
        if not p.exists():
            continue
        current = None
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            m = LOG_TIME_RE.match(line)
            if m:
                current = m.group(1)
            if current and current >= since_dt.strftime("%Y-%m-%d %H:%M:%S"):
                out.append((current.replace(" ", "T"), "log: " + line))
    return out


def build_report(hours: float, now: datetime | None = None, db: Path | None = None) -> str:
    now = now or datetime.now()
    since_dt = now - timedelta(hours=hours)
    since = since_dt.isoformat(timespec="seconds")
    items = _rows(db or _db_path(), since) + _log_lines(since_dt)
    items.sort(key=lambda x: x[0])
    scrub = make_scrubber(_env_secret_values())
    head = (f"Jarvis debug report, {since} -> {now.isoformat(timespec='seconds')} ({len(items)} entries)\n"
            "Secrets and email addresses are masked. Read it before sending.\n\n")
    return head + "\n".join(scrub(f"[{ts}] {text}") for ts, text in items) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=3.0, help="how far back to look (default 3)")
    ap.add_argument("--out", default=str(ROOT / "debug_report.txt"))
    args = ap.parse_args()
    report = build_report(args.hours)
    Path(args.out).write_text(report, encoding="utf-8")
    print(f"Wrote {args.out} ({report.count(chr(10))} lines). Read it, then send it.")


if __name__ == "__main__":
    main()
