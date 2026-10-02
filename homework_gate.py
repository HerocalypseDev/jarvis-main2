"""Confirmation add-on for the owner's homework app (PRIVATE: every homework_* file is kept out of the public export).

jarvis.py loads every `*_gate.py` file next to it (see "Confirmation add-ons" in jarvis.py). This one puts the homework
app's two irreversible tools behind the staged confirmation (spoken yes / dashboard Approve), and lets several homework
deletes in one request wait for a single yes. Matched on the MCP server's REAL tool name, so it holds whatever the
server is called in mcp_servers.json. Pure functions: no jarvis import, no network.
"""

from __future__ import annotations

import re

CONFIRM = {"delete_homework", "set_student_password"}
BATCH_MAX = {"delete_homework": 10}  # tools whose calls may share one pending confirmation, and how many


def confirm_reason(real: str, inp: dict) -> str | None:
    if real == "delete_homework":
        title = str(inp.get("confirm_title") or inp.get("homework_id") or "that homework")[:80]
        return f'permanently delete the homework "{title}" with every answer, file record and grade'
    if real == "set_student_password":
        who = str(inp.get("student") or "a student")[:40]
        return f"change {who}'s homework-app password and sign them out everywhere"
    return None


def batch_key(real: str, inp: dict) -> str:
    return str(inp.get("homework_id") or "")


def label(real: str, inp: dict) -> str:
    title = str(inp.get("confirm_title") or "").strip()[:60]
    return f'"{title}"' if title else f"id {str(inp.get('homework_id') or '?')[:12]}"


def _join(labels: list[str]) -> str:
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]


def batch_reason(real: str, labels: list[str]) -> str:
    return f"permanently delete {len(labels)} homeworks ({_join(labels)}) with every answer, file record and grade"


def staged_message(real: str, labels: list[str]) -> str:
    return f"{len(labels)} homework deletions staged, not run: {_join(labels)}. Say yes to delete all {len(labels)}."


def duplicate_message(real: str, new_label: str, labels: list[str]) -> str:
    n = len(labels)
    return (f"{new_label} is already staged, not run. {n} homework deletion{'s' if n != 1 else ''} waiting: "
            f"{_join(labels)}. Say yes to delete {'all ' + str(n) if n > 1 else 'it'}.")


def full_message(real: str, n: int, limit: int) -> str:
    return (f"Not added: at most {limit} homework deletions can wait for one yes. "
            f"{n} are staged, not run; say yes to delete them, then ask again for the rest.")


def summary(real: str, n: int, failures: list[tuple[str, str]]) -> str:
    if not failures:
        return f"Deleted {n} homeworks."
    parts = []
    for lab, why in failures:
        why = re.sub(r"^(?:tool failed:\s*)?(?:homework app:\s*)?", "", why.strip(), flags=re.I)
        parts.append(f"{lab} ({why[:80].rstrip('.')})")
    return f"Deleted {n - len(failures)} of {n} homeworks. Not deleted: " + "; ".join(parts) + "."
