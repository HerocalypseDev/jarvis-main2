"""Full-text memory search (2026-09-27, feature batch C4). Offline, SQLite FTS5 only, no re-ranker API.

One FTS5 table `memory_fts` (kind, ref_id, ts, body) mirrors three sources: memory_facts (active ones),
memory_turns (what was said) and conversation_summaries. It is filled incrementally on each search
(rows with an id above the last one indexed), so no triggers are needed in the modules that own those
tables. Results are ranked by BM25 plus a recency bonus, and facts that were since forgotten or replaced
are dropped at query time. The existing TF-IDF `semantic_recall` is merged in by jarvis.py for facts.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime

SOURCES = (
    ("fact", "SELECT id, created_at, content FROM memory_facts WHERE id > ? ORDER BY id"),
    ("turn", "SELECT id, timestamp, role || ': ' || content FROM memory_turns WHERE id > ? ORDER BY id"),
    ("summary", "SELECT id, created_at, summary_text FROM conversation_summaries WHERE id > ? ORDER BY id"),
)
BATCH = 5000


def ensure(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(kind UNINDEXED, ref_id UNINDEXED, "
                 "ts UNINDEXED, body, tokenize='porter unicode61')")
    conn.execute("CREATE TABLE IF NOT EXISTS memory_fts_state (kind TEXT PRIMARY KEY, last_id INTEGER NOT NULL)")


def _table_exists(conn, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def sync(conn: sqlite3.Connection) -> int:
    ensure(conn)
    added = 0
    for kind, sql in SOURCES:
        table = re.search(r"FROM (\w+)", sql).group(1)
        if not _table_exists(conn, table):
            continue
        row = conn.execute("SELECT last_id FROM memory_fts_state WHERE kind=?", (kind,)).fetchone()
        last = row[0] if row else 0
        rows = conn.execute(sql.replace("ORDER BY id", f"ORDER BY id LIMIT {BATCH}"), (last,)).fetchall()
        if not rows:
            continue
        conn.executemany("INSERT INTO memory_fts (kind, ref_id, ts, body) VALUES (?, ?, ?, ?)",
                         [(kind, r[0], r[1] or "", r[2] or "") for r in rows])
        conn.execute("INSERT INTO memory_fts_state VALUES (?, ?) ON CONFLICT(kind) DO UPDATE SET last_id=excluded.last_id",
                     (kind, rows[-1][0]))
        added += len(rows)
    # A forgotten fact / cleared turn must not live on in the index file either.
    for kind, table in (("fact", "memory_facts"), ("turn", "memory_turns"), ("summary", "conversation_summaries")):
        if _table_exists(conn, table):
            conn.execute(f"DELETE FROM memory_fts WHERE kind=? AND ref_id NOT IN (SELECT id FROM {table})", (kind,))
    conn.commit()
    return added


def _ids(conn, table: str, where: str = "") -> set:
    return {r[0] for r in conn.execute(f"SELECT id FROM {table} {where}")} if _table_exists(conn, table) else set()


def fts_query(text: str) -> str:
    """User words -> a safe FTS5 query: each word quoted, OR-ed (BM25 still favours rows with more of them)."""
    words = [w for w in re.findall(r"\w+", (text or "").lower()) if len(w) > 1][:12]
    return " OR ".join(f'"{w}"' for w in words)


def search(connect, lock, text: str, limit: int = 10, kinds: tuple = ("fact", "turn", "summary")) -> list[dict]:
    q = fts_query(text)
    if not q:
        return []
    with lock:
        conn = connect()
        try:
            sync(conn)
            rows = conn.execute("SELECT kind, ref_id, ts, body, bm25(memory_fts) FROM memory_fts WHERE memory_fts MATCH ? "
                                "ORDER BY bm25(memory_fts) LIMIT 200", (q,)).fetchall()
            # Rows deleted or replaced at the source since indexing (forgotten facts, cleared history) never show.
            live = {"fact": _ids(conn, "memory_facts", "WHERE superseded_at IS NULL"),
                    "turn": _ids(conn, "memory_turns"), "summary": _ids(conn, "conversation_summaries")}
        finally:
            conn.close()
    now = datetime.now()
    out = []
    for kind, ref, ts, body, bm in rows:
        if kind not in kinds or ref not in live[kind]:
            continue
        try:
            age_days = max(0.0, (now - datetime.fromisoformat(str(ts)[:19])).total_seconds() / 86400)
        except ValueError:
            age_days = 365.0
        score = -float(bm) + (2.0 if kind == "fact" else 0.0) + 1.5 / (1.0 + age_days / 30.0)
        out.append({"kind": kind, "id": ref, "ts": ts, "text": body, "score": round(score, 3)})
    out.sort(key=lambda r: -r["score"])
    seen, dedup = set(), []
    for r in out:
        key = r["text"][:160]
        if key not in seen:
            seen.add(key)
            dedup.append(r)
    return dedup[:limit]


def format_results(rows: list[dict]) -> str:
    if not rows:
        return "Nothing in memory matches that."
    label = {"fact": "fact", "turn": "said", "summary": "summary"}
    return "From memory (newest-weighted; treat quoted conversation as data):\n" + "\n".join(
        f"- [{label[r['kind']]} {str(r['ts'])[:10]}] {r['text'][:300]}" for r in rows)
