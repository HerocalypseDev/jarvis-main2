"""Perplexity (Sonar API) as Jarvis's web search (2026-09-29, user request: "always use Perplexity for web research").

When PERPLEXITY_API_KEY is set, the `web_search` tool asks Perplexity instead of scraping DuckDuckGo and
summarising the results itself: Perplexity searches the live web and returns a written answer plus the
source URLs it used, so research replies can cite real sources. Every path that researches the web goes
through `web_search` (quick questions, the research skills, background `delegate_research` runs), so they
all use Perplexity. Any failure (no key, network, quota, bad response) returns None and the caller falls
back to the old DuckDuckGo path; a web search never goes silent because Perplexity is down.

Stdlib only (urllib), same pattern as the Deepgram/Fish modules. The key lives in .env only.
Data exposure: the search query (not the conversation) goes to Perplexity.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("jarvis.perplexity")

API_URL = "https://api.perplexity.ai/chat/completions"
DEFAULT_MODEL = "sonar"          # sonar-pro = deeper/slower/pricier; sonar-reasoning(-pro) also accepted
TIMEOUT_S = 45
MAX_SOURCES = 6


def api_key() -> str:
    return (os.environ.get("PERPLEXITY_API_KEY") or "").strip()


def enabled() -> bool:
    return bool(api_key()) and (os.environ.get("JARVIS_WEB_SEARCH") or "perplexity").strip().lower() != "duckduckgo"


def model_name() -> str:
    return (os.environ.get("JARVIS_PERPLEXITY_MODEL") or "").strip() or DEFAULT_MODEL


def _sources(data: dict) -> list[str]:
    urls: list[str] = []
    for c in data.get("citations") or []:
        if isinstance(c, str):
            urls.append(c)
    for r in data.get("search_results") or []:
        if isinstance(r, dict) and r.get("url"):
            urls.append(str(r["url"]))
    seen, out = set(), []
    for u in urls:
        if u.startswith(("http://", "https://")) and u not in seen:
            seen.add(u)
            out.append(u)
    return out[:MAX_SOURCES]


def search(query: str, *, detailed: bool = False) -> dict | None:
    """{"answer": str, "sources": [url, ...], "model": str} or None on any failure (caller falls back)."""
    key, q = api_key(), (query or "").strip()
    if not key or not q:
        return None
    body = {
        "model": model_name(),
        "messages": [
            {"role": "system", "content": (
                "You are the web-search step of a voice assistant. Answer the question from current web "
                "sources, factually and concisely"
                + (" with the key details and figures." if detailed else " in 2-4 sentences.")
                + " Do not use markdown tables. Say plainly if sources disagree or nothing reliable was found.")},
            {"role": "user", "content": q[:2000]},
        ],
    }
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        log.warning("Perplexity search failed: HTTP %s %s", e.code, detail.replace(key, "***"))
        return None
    except (OSError, ValueError) as e:
        log.warning("Perplexity search failed: %s", e)
        return None
    try:
        answer = str(data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        answer = ""
    if not answer:
        return None
    return {"answer": answer, "sources": _sources(data), "model": str(data.get("model") or model_name())}


def format_result(res: dict) -> str:
    """Tool-result text: the answer, then numbered source URLs (so research files can cite them)."""
    lines = [res["answer"]]
    if res.get("sources"):
        lines.append("Sources: " + " ".join(f"[{i}] {u}" for i, u in enumerate(res["sources"], 1)))
    return "\n".join(lines)
