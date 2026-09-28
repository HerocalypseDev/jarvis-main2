"""Tool narrowing (2026-09-28): send the model only the tools a command is likely to need.

Jarvis offers ~130 built-in tools plus every connected MCP tool. Tool-picking accuracy drops
sharply past ~30-50 tools, and small models (Gemini flash-lite) suffer most. This module ranks
the full list against the command with BM25 over each tool's name, description and parameter
names, and returns a short list: an always-on core, the best matches, and a `find_tools`
meta-tool the model can call to pull in more by keyword for the next round.

Pure functions, no model call, no network. Never a safety boundary: the catastrophic gate is
enforced in _execute_tool whatever tools were offered, and a tool the model names that was not
offered still goes through the same gate.
"""
from __future__ import annotations

import math
import re
from collections import Counter

FIND_TOOLS_NAME = "find_tools"

FIND_TOOLS_SCHEMA = {
    "name": FIND_TOOLS_NAME,
    "description": (
        "Only a short list of your tools is loaded for this command. If none of them fits what the "
        "user asked, call this with a few keywords describing the capability you need (e.g. "
        "'whatsapp message', 'resize window', 'calendar event', 'sleep mode'). The matching tools "
        "become available on your next step. Do not tell the user you lack a tool before trying this."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Keywords for the capability you need"}},
        "required": ["query"],
    },
}

# Always offered: cheap, general, and needed across many kinds of command.
CORE_TOOLS = {
    "remember_fact", "recall_facts", "memory_search", "create_reminder", "list_reminders",
    "schedule_jarvis_task", "delegate_to_claude_code", "change_jarvis_code", "list_background_tasks",
    "web_search", "open_app", "open_url", "run_shell", "read_file", "write_file", "system_status",
    "briefing", "self_check",
}

_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "my", "me", "i", "you",
    "it", "is", "are", "be", "can", "could", "please", "jarvis", "this", "that", "what", "whats",
    "how", "do", "does", "your", "from", "at", "by", "as", "if", "then", "use", "tool", "when",
    "will", "would", "should", "into", "about", "some", "any", "all", "get", "set", "make",
}


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower().replace("_", " ").replace("-", " "))
    out = []
    for w in words:
        if w in _STOP or len(w) < 2:
            continue
        out.append(w)
        if len(w) > 4 and w.endswith("s"):  # crude plural folding: "reminders" ~ "reminder"
            out.append(w[:-1])
    return out


def _tool_text(tool: dict) -> str:
    props = ((tool.get("input_schema") or {}).get("properties") or {})
    parts = [tool.get("name", "")] * 3  # the name matters most
    parts.append(tool.get("description", "")[:600])
    parts.extend(props.keys())
    for p in props.values():
        if isinstance(p, dict):
            enum = p.get("enum")
            if isinstance(enum, list):
                parts.extend(str(e) for e in enum[:20])
    return " ".join(parts)


class ToolIndex:
    """BM25 over tool text. Built once per distinct tool list (cheap: ~200 tools, <10 ms)."""

    def __init__(self, tools: list[dict]):
        self.tools = [t for t in tools if t.get("name")]
        self.docs = [Counter(_tokens(_tool_text(t))) for t in self.tools]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avg = (sum(self.lens) / len(self.lens)) if self.lens else 1.0
        df: Counter = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs) or 1
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    def scores(self, query: str, k1: float = 1.4, b: float = 0.75) -> list[tuple[float, dict]]:
        q = _tokens(query)
        out = []
        for tool, d, ln in zip(self.tools, self.docs, self.lens):
            s = 0.0
            for w in q:
                f = d.get(w)
                if f:
                    s += self.idf.get(w, 0.0) * f * (k1 + 1) / (f + k1 * (1 - b + b * ln / self.avg))
            if s > 0:
                out.append((s, tool))
        out.sort(key=lambda x: -x[0])
        return out

    def search(self, query: str, limit: int = 8, exclude: set[str] | None = None) -> list[dict]:
        exclude = exclude or set()
        return [t for _, t in self.scores(query) if t["name"] not in exclude][:limit]


_index_cache: dict = {"key": None, "index": None}


def index_for(tools: list[dict]) -> ToolIndex:
    key = tuple(t.get("name", "") for t in tools)
    if _index_cache["key"] != key:
        _index_cache.update(key=key, index=ToolIndex(tools))
    return _index_cache["index"]


def select(query: str, tools: list[dict], limit: int = 28, context: str = "",
           core: set[str] | None = None) -> list[dict]:
    """The core tools, then the best BM25 matches for the command (plus a little recent context,
    weighted lower), then find_tools. Order is stable (original list order) so the schema a model
    sees doesn't reshuffle between near-identical commands."""
    core = CORE_TOOLS if core is None else core
    idx = index_for(tools)
    picked: set[str] = {t["name"] for t in tools if t.get("name") in core}
    # A tool named outright ("use code_search") is always included.
    low = (query or "").lower()
    for t in tools:
        n = t.get("name", "")
        if n and (n.lower() in low or n.lower().replace("_", " ") in low):
            picked.add(n)
    ranked = idx.scores(query)
    if context:
        seen = {t["name"] for _, t in ranked}
        ranked += [(s * 0.4, t) for s, t in idx.scores(context) if t["name"] not in seen]
        ranked.sort(key=lambda x: -x[0])
    for _, t in ranked:
        if len(picked) >= limit:
            break
        picked.add(t["name"])
    chosen = [t for t in tools if t.get("name") in picked]
    return chosen + [FIND_TOOLS_SCHEMA]


def find_more(query: str, tools: list[dict], offered: set[str], limit: int = 8) -> tuple[list[dict], str]:
    """For a find_tools call: the new tools to add, and the text returned to the model."""
    found = index_for(tools).search(query, limit=limit, exclude=offered | {FIND_TOOLS_NAME})
    if not found:
        return [], f"No other tools match '{query}'. Answer with the tools you have, or tell the user plainly."
    lines = "; ".join(f"{t['name']}: {(t.get('description') or '').split('.')[0][:90]}" for t in found)
    return found, f"These tools are now available on your next step: {lines}"
