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


# =============================================================================================
# Local estimate: every Claude call's `usage` block x list price, stored in `api_usage`.
# Needs no admin key and covers exactly what Jarvis itself spent (not other apps on the same key).
# =============================================================================================
import sqlite3
import threading
import time

# USD per million tokens. Longest-prefix match on the model id; an unrecognised model falls back
# to Haiku 4.5 rates and the summary flags the figure as approximate. Update when prices change.
PRICES: dict[str, dict[str, float]] = {
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00, "read": 0.10, "w5m": 1.25, "w1h": 2.00},
    "claude-sonnet-4": {"in": 3.00, "out": 15.00, "read": 0.30, "w5m": 3.75, "w1h": 6.00},
    "claude-opus-4-5": {"in": 5.00, "out": 25.00, "read": 0.50, "w5m": 6.25, "w1h": 10.00},
    # Gemini paid-tier list prices (ai.google.dev/gemini-api/docs/pricing). Implicit caching has no
    # write charge, so w5m/w1h just mirror the input rate. The free tier actually bills $0 — these
    # are "what it would cost" figures; the real free-tier constraint is tokens/requests per
    # minute and day, which the dashboard shows as token totals.
    "gemini-3.5-flash-lite": {"in": 0.30, "out": 2.50, "read": 0.03, "w5m": 0.30, "w1h": 0.30},
    "gemini-3.5-flash": {"in": 1.50, "out": 9.00, "read": 0.15, "w5m": 1.50, "w1h": 1.50},
    "gemini-3.1-flash-lite": {"in": 0.25, "out": 1.50, "read": 0.025, "w5m": 0.25, "w1h": 0.25},
    "gemini-2.5-flash-lite": {"in": 0.10, "out": 0.40, "read": 0.01, "w5m": 0.10, "w1h": 0.10},
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50, "read": 0.03, "w5m": 0.30, "w1h": 0.30},
}
_FALLBACK = PRICES["claude-haiku-4-5"]
USAGE_RETENTION_DAYS = 400


def _rates(model: str) -> tuple[dict[str, float], bool]:
    best = max((p for p in PRICES if (model or "").startswith(p)), key=len, default=None)
    return (PRICES[best], True) if best else (_FALLBACK, False)


def compute_cost(model: str, usage: dict) -> tuple[float, float, bool]:
    """(cost_usd, cache_saved_usd, price_known) for one response's `usage` block."""
    rates, known = _rates(model)
    fresh = usage.get("input_tokens", 0) or 0
    read = usage.get("cache_read_input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    write_total = usage.get("cache_creation_input_tokens", 0) or 0
    detail = usage.get("cache_creation") or {}
    w1h = detail.get("ephemeral_1h_input_tokens", 0) or 0
    w5m = detail.get("ephemeral_5m_input_tokens", write_total - w1h) or 0
    cost = (
        fresh * rates["in"] + out * rates["out"] + read * rates["read"]
        + w5m * rates["w5m"] + w1h * rates["w1h"]
    ) / 1e6
    saved = read * (rates["in"] - rates["read"]) / 1e6
    return cost, saved, known


def _ensure_usage_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_usage ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, model TEXT NOT NULL, "
        "input_tokens INTEGER, cache_read_tokens INTEGER, cache_write_tokens INTEGER, "
        "output_tokens INTEGER, cost_usd REAL NOT NULL, saved_usd REAL NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_ts ON api_usage(ts)")


def record_usage(connect: Callable[[], sqlite3.Connection], lock, model: str, usage: dict) -> None:
    """Best-effort: never raises and never blocks the caller for long. A failure here must not
    affect the Claude call whose usage it records."""
    try:
        if not usage:
            return
        cost, saved, _ = compute_cost(model, usage)
        with lock:
            conn = connect()
            try:
                _ensure_usage_table(conn)
                conn.execute(
                    "INSERT INTO api_usage (ts, model, input_tokens, cache_read_tokens, "
                    "cache_write_tokens, output_tokens, cost_usd, saved_usd) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        time.time(), model or "unknown", usage.get("input_tokens", 0) or 0,
                        usage.get("cache_read_input_tokens", 0) or 0,
                        usage.get("cache_creation_input_tokens", 0) or 0,
                        usage.get("output_tokens", 0) or 0, cost, saved,
                    ),
                )
                conn.execute(
                    "DELETE FROM api_usage WHERE ts < ?", (time.time() - USAGE_RETENTION_DAYS * 86400,)
                )
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        log.debug("api_usage record failed: %s", e)


def local_summary(connect: Callable[[], sqlite3.Connection], lock, now: float | None = None) -> dict:
    """Totals for the dashboard/tool. Periods use the machine's local calendar (today = since
    local midnight, month = calendar month to date, week = last 7 local days incl. today)."""
    now = now or time.time()
    lt = time.localtime(now)
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    starts = {
        "today": midnight,
        "week": midnight - 6 * 86400,
        "month": time.mktime((lt.tm_year, lt.tm_mon, 1, 0, 0, 0, 0, 0, -1)),
        "all_time": 0.0,
    }
    out: dict = {"periods": {}, "by_model": [], "daily": [], "estimate_note": (
        "Estimated from token counts x list price for calls made by Jarvis only; the "
        "provider's own console is the source of truth. Gemini figures are paid-tier equivalents "
        "(the free tier bills $0 but is limited by tokens/requests per minute and day)."
    )}
    with lock:
        conn = connect()
        try:
            _ensure_usage_table(conn)
            for name, start in starts.items():
                row = conn.execute(
                    "SELECT COALESCE(SUM(cost_usd),0), COUNT(*), COALESCE(SUM(input_tokens),0), "
                    "COALESCE(SUM(cache_read_tokens),0), COALESCE(SUM(cache_write_tokens),0), "
                    "COALESCE(SUM(output_tokens),0), COALESCE(SUM(saved_usd),0) "
                    "FROM api_usage WHERE ts >= ?", (start,),
                ).fetchone()
                out["periods"][name] = {
                    "cost_usd": row[0], "calls": row[1], "input_tokens": row[2],
                    "cache_read_tokens": row[3], "cache_write_tokens": row[4],
                    "output_tokens": row[5], "cache_saved_usd": row[6],
                }
            out["by_model"] = [
                {"model": m, "cost_usd": c, "calls": n, "tokens": t}
                for m, c, n, t in conn.execute(
                    "SELECT model, SUM(cost_usd), COUNT(*), SUM(COALESCE(input_tokens,0) + "
                    "COALESCE(cache_read_tokens,0) + COALESCE(cache_write_tokens,0) + "
                    "COALESCE(output_tokens,0)) FROM api_usage WHERE ts >= ? "
                    "GROUP BY model ORDER BY SUM(cost_usd) DESC", (starts["month"],),
                )
            ]
            by_day = dict(conn.execute(
                "SELECT strftime('%Y-%m-%d', ts, 'unixepoch', 'localtime'), SUM(cost_usd) "
                "FROM api_usage WHERE ts >= ? GROUP BY 1", (midnight - 13 * 86400,),
            ).fetchall())
        finally:
            conn.close()
    for i in range(13, -1, -1):
        day = time.strftime("%Y-%m-%d", time.localtime(midnight - i * 86400 + 3600))
        out["daily"].append({"date": day, "cost_usd": by_day.get(day, 0.0)})
    out["unknown_price_models"] = [
        m["model"] for m in out["by_model"] if not _rates(m["model"])[1]
    ]
    return out


def format_local_summary(s: dict) -> str:
    p = s["periods"]
    if not p["all_time"]["calls"]:
        return "No Jarvis API usage has been recorded yet, so there's no estimate to give."
    text = (
        f"Estimated Claude spend from Jarvis: ${p['today']['cost_usd']:.2f} today, "
        f"${p['week']['cost_usd']:.2f} over the last 7 days, ${p['month']['cost_usd']:.2f} this month, "
        f"${p['all_time']['cost_usd']:.2f} in total since tracking began."
    )
    if p["month"]["cache_saved_usd"] > 0.005:
        text += f" Prompt caching saved about ${p['month']['cache_saved_usd']:.2f} this month."
    if s["unknown_price_models"]:
        text += " Some usage is on a model with unknown pricing, so that part is approximate."
    return text
