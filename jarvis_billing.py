"""Anthropic API spend lookup via the Usage & Cost Admin API (GET /v1/organizations/cost_report).

Needs an *Admin* API key (ANTHROPIC_ADMIN_API_KEY in .env, starts with sk-ant-admin) — the normal
ANTHROPIC_API_KEY can only send requests, it can't read billing. Read-only: this module never
creates, changes or deletes anything on the account, and the key is only ever sent to
api.anthropic.com in the x-api-key header (never logged or returned in tool output).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable

log = logging.getLogger("jarvis")

COST_REPORT_URL = "https://api.anthropic.com/v1/organizations/cost_report"
MAX_PAGES = 5


def _default_get(url: str, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def fetch_cost_buckets(
    admin_key: str, days: int, now: datetime | None = None, http_get: Callable = _default_get
) -> list[dict]:
    """Daily cost buckets for the last `days` UTC days (today included), following pagination.
    Raises on HTTP/network errors; the caller turns that into a readable message."""
    now = now or datetime.now(timezone.utc)
    start = (now - timedelta(days=max(1, days) - 1)).strftime("%Y-%m-%dT00:00:00Z")
    params = [
        ("starting_at", start),
        ("ending_at", now.strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("bucket_width", "1d"),
        ("group_by[]", "description"),
        ("limit", str(min(max(days, 1), 31))),
    ]
    headers = {"x-api-key": admin_key, "anthropic-version": "2023-06-01"}
    buckets: list[dict] = []
    page = None
    for _ in range(MAX_PAGES):
        q = params + ([("page", page)] if page else [])
        data = http_get(f"{COST_REPORT_URL}?{urllib.parse.urlencode(q)}", headers, 20)
        buckets.extend(data.get("data") or [])
        page = data.get("next_page")
        if not (data.get("has_more") and page):
            break
    return buckets


def _dollars(amount) -> float:
    # The API reports amounts in the lowest currency unit (cents) as a decimal string.
    try:
        return float(amount) / 100.0
    except (TypeError, ValueError):
        return 0.0


def summarize(buckets: list[dict], days: int, today: str | None = None) -> str:
    """Spoken-friendly one-paragraph summary: total, today, and top models."""
    total = 0.0
    today_total = 0.0
    by_model: dict[str, float] = defaultdict(float)
    for b in buckets:
        day_cost = 0.0
        for r in b.get("results") or []:
            cost = _dollars(r.get("amount"))
            day_cost += cost
            by_model[r.get("model") or r.get("description") or "other"] += cost
        total += day_cost
        if today and (b.get("starting_at") or "").startswith(today):
            today_total = day_cost
    if not buckets or total == 0:
        return f"No API spend recorded in the last {days} day{'s' if days != 1 else ''}."
    top = sorted(by_model.items(), key=lambda kv: kv[1], reverse=True)[:3]
    top_text = ", ".join(f"{name} ${cost:.2f}" for name, cost in top if cost > 0)
    parts = [f"API spend over the last {days} day{'s' if days != 1 else ''} is ${total:.2f}"]
    if today is not None:
        parts.append(f"${today_total:.2f} of it today")
    text = ", ".join(parts) + "."
    if top_text:
        text += f" Biggest: {top_text}."
    return text


def get_api_spend(admin_key: str, days: int = 30, http_get: Callable = _default_get) -> str:
    """Tool entry point. Never raises; every failure becomes a plain-English sentence."""
    if not (admin_key or "").strip():
        return (
            "No admin key is set. Add ANTHROPIC_ADMIN_API_KEY (an sk-ant-admin key from the "
            "Anthropic Console's Admin keys page) to the .env file and restart Jarvis."
        )
    days = max(1, min(int(days or 30), 90))
    now = datetime.now(timezone.utc)
    try:
        buckets = fetch_cost_buckets(admin_key.strip(), days, now, http_get)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return "Anthropic rejected the admin key. Check ANTHROPIC_ADMIN_API_KEY is an sk-ant-admin key."
        return f"Couldn't read API spend: Anthropic returned HTTP {e.code}."
    except Exception as e:
        log.warning("API spend lookup failed: %s", e)
        return "Couldn't read API spend right now."
    return summarize(buckets, days, today=now.strftime("%Y-%m-%d"))
