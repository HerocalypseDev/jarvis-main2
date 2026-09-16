"""Contextual memory enhancement for Jarvis.

Extends jarvis.py's existing `memory_facts` table (keyword-searchable, category-tagged
facts) with three things it doesn't have:
  - relationships between facts (`link_facts`/`related_facts`) — e.g. linking a
    "prefers dark mode" preference to the "editor_theme" decision that caused it.
  - decision history with rationale/alternatives/outcome, separate from one-line facts.
  - remembered code patterns/conventions the user prefers, taggable by language.
  - semantic recall: a small pure-Python TF-IDF + cosine-similarity search across facts,
    decisions, and code patterns together, so a query can surface a relevant memory even
    when the wording doesn't literally overlap with a SQL LIKE match.

Self-contained: owns its own tables in the same jarvis_memory.db file jarvis.py already
uses, with its own connection/lock, so importing this module has no ordering dependency
on jarvis.py's own initialization.
"""

from __future__ import annotations

import logging
import math
import os
import re
import sqlite3
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path

log = logging.getLogger("jarvis.memory_enhance")

MAX_RESULT_CHARS = 4000
_TOKEN_RE = re.compile(r"[a-z0-9]+")

_db_lock = threading.Lock()


def _db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "jarvis_memory.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS memory_relations ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "fact_id_a INTEGER NOT NULL, "
        "fact_id_b INTEGER NOT NULL, "
        "relation TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS decision_history ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "decision TEXT NOT NULL, "
        "rationale TEXT, "
        "alternatives TEXT, "
        "project TEXT, "
        "created_at TEXT NOT NULL, "
        "outcome TEXT, "
        "outcome_updated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS code_patterns ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "language TEXT, "
        "pattern TEXT NOT NULL, "
        "example TEXT, "
        "note TEXT, "
        "created_at TEXT NOT NULL)"
    )
    return conn


# --- relationships between facts -----------------------------------------------------

def link_facts(fact_id_a: int, fact_id_b: int, relation: str) -> str:
    """Records a directed relationship between two memory_facts rows (by id, as shown by
    recall_facts) — e.g. relation='caused_by', 'supersedes_context', 'related_to'."""
    now = datetime.now().isoformat(timespec="seconds")
    with _db_lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO memory_relations (fact_id_a, fact_id_b, relation, created_at) "
                "VALUES (?, ?, ?, ?)",
                (fact_id_a, fact_id_b, relation.strip() or "related_to", now),
            )
            conn.commit()
        except sqlite3.Error as e:
            log.warning("link_facts failed: %s", e)
            return f"Failed to link facts: {e}"
        finally:
            conn.close()
    return f"Linked fact {fact_id_a} -> fact {fact_id_b} ({relation})."


def related_facts(fact_id: int) -> list[tuple]:
    with _db_lock:
        conn = _connect()
        try:
            return conn.execute(
                "SELECT fact_id_a, fact_id_b, relation, created_at FROM memory_relations "
                "WHERE fact_id_a = ? OR fact_id_b = ? ORDER BY id DESC",
                (fact_id, fact_id),
            ).fetchall()
        finally:
            conn.close()


# --- decision history ------------------------------------------------------------------

def remember_decision(decision: str, rationale: str = "", alternatives: str = "", project: str = "") -> str:
    """Records a decision with why it was made and what else was considered — richer than
    a one-line memory_facts entry, meant for choices worth revisiting later (architecture,
    tool choice, a tradeoff)."""
    now = datetime.now().isoformat(timespec="seconds")
    with _db_lock:
        conn = _connect()
        try:
            cur = conn.execute(
                "INSERT INTO decision_history "
                "(decision, rationale, alternatives, project, created_at, outcome, outcome_updated_at) "
                "VALUES (?, ?, ?, ?, ?, NULL, NULL)",
                (decision.strip(), rationale.strip(), alternatives.strip(), project.strip(), now),
            )
            conn.commit()
            row_id = cur.lastrowid
        except sqlite3.Error as e:
            log.warning("remember_decision failed: %s", e)
            return f"Failed to record decision: {e}"
        finally:
            conn.close()
    return f"Recorded decision #{row_id}: {decision}"


def update_decision_outcome(decision_id: int, outcome: str) -> str:
    """Records how a past decision actually played out — call this once the result is known."""
    now = datetime.now().isoformat(timespec="seconds")
    with _db_lock:
        conn = _connect()
        try:
            cur = conn.execute(
                "UPDATE decision_history SET outcome = ?, outcome_updated_at = ? WHERE id = ?",
                (outcome.strip(), now, decision_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                return f"No decision with id {decision_id}."
        except sqlite3.Error as e:
            log.warning("update_decision_outcome failed: %s", e)
            return f"Failed to update decision: {e}"
        finally:
            conn.close()
    return f"Updated outcome for decision #{decision_id}."


def list_decisions(project: str = "", limit: int = 10) -> str:
    with _db_lock:
        conn = _connect()
        try:
            if project.strip():
                rows = conn.execute(
                    "SELECT id, decision, rationale, outcome, created_at FROM decision_history "
                    "WHERE project = ? ORDER BY id DESC LIMIT ?",
                    (project.strip(), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, decision, rationale, outcome, created_at FROM decision_history "
                    "ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        finally:
            conn.close()
    if not rows:
        return "No decisions recorded yet."
    lines = []
    for rid, decision, rationale, outcome, created_at in rows:
        line = f"#{rid} ({created_at[:10]}): {decision}"
        if rationale:
            line += f" — because {rationale}"
        if outcome:
            line += f" [outcome: {outcome}]"
        lines.append(line)
    return "\n".join(lines)[:MAX_RESULT_CHARS]


# --- code patterns ------------------------------------------------------------------

def remember_code_pattern(pattern: str, language: str = "", example: str = "", note: str = "") -> str:
    """Records a code style/pattern the user prefers (e.g. 'uses dataclasses over plain
    dicts for config', 'prefers early returns over nested if/else')."""
    now = datetime.now().isoformat(timespec="seconds")
    with _db_lock:
        conn = _connect()
        try:
            cur = conn.execute(
                "INSERT INTO code_patterns (language, pattern, example, note, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (language.strip(), pattern.strip(), example.strip(), note.strip(), now),
            )
            conn.commit()
            row_id = cur.lastrowid
        except sqlite3.Error as e:
            log.warning("remember_code_pattern failed: %s", e)
            return f"Failed to record code pattern: {e}"
        finally:
            conn.close()
    return f"Recorded code pattern #{row_id}: {pattern}"


def list_code_patterns(language: str = "", limit: int = 15) -> str:
    with _db_lock:
        conn = _connect()
        try:
            if language.strip():
                rows = conn.execute(
                    "SELECT id, language, pattern, note FROM code_patterns "
                    "WHERE language = ? ORDER BY id DESC LIMIT ?",
                    (language.strip(), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, language, pattern, note FROM code_patterns ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        finally:
            conn.close()
    if not rows:
        return "No code patterns recorded yet."
    lines = []
    for rid, language, pattern, note in rows:
        line = f"#{rid} [{language or 'any'}] {pattern}"
        if note:
            line += f" ({note})"
        lines.append(line)
    return "\n".join(lines)[:MAX_RESULT_CHARS]


# --- semantic recall: pure-Python TF-IDF + cosine similarity --------------------------

def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _tfidf_vectors(docs: list[list[str]]) -> tuple[list[dict[str, float]], dict[str, float]]:
    """Returns (per-doc TF-IDF weight dicts, idf table) for a small in-memory corpus —
    good enough at personal-assistant scale (hundreds to low thousands of memories),
    intentionally not a dependency on numpy/sklearn for something this small."""
    n_docs = len(docs)
    df: Counter = Counter()
    for tokens in docs:
        for term in set(tokens):
            df[term] += 1
    idf = {term: math.log((1 + n_docs) / (1 + count)) + 1 for term, count in df.items()}

    vectors: list[dict[str, float]] = []
    for tokens in docs:
        tf = Counter(tokens)
        total = sum(tf.values()) or 1
        vectors.append({term: (count / total) * idf.get(term, 0.0) for term, count in tf.items()})
    return vectors, idf


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[t] * b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in a.values())) or 1.0
    norm_b = math.sqrt(sum(v * v for v in b.values())) or 1.0
    return dot / (norm_a * norm_b)


def semantic_recall(query: str, limit: int = 5) -> str:
    """Ranks memory_facts, decision_history, and code_patterns by TF-IDF cosine similarity
    to `query`, instead of jarvis.py's recall_facts which is exact keyword (SQL LIKE) only.
    Falls back to reporting no match rather than returning irrelevant rows."""
    query = (query or "").strip()
    if not query:
        return "Give me something to search for."

    with _db_lock:
        conn = _connect()
        try:
            fact_rows = conn.execute(
                "SELECT id, category, content FROM memory_facts WHERE superseded_at IS NULL"
            ).fetchall()
            decision_rows = conn.execute(
                "SELECT id, decision, rationale FROM decision_history"
            ).fetchall()
            pattern_rows = conn.execute(
                "SELECT id, pattern, note FROM code_patterns"
            ).fetchall()
        except sqlite3.Error as e:
            log.warning("semantic_recall read failed: %s", e)
            return f"Semantic recall failed: {e}"
        finally:
            conn.close()

    corpus_texts: list[str] = []
    corpus_labels: list[str] = []
    for fid, category, content in fact_rows:
        corpus_texts.append(content)
        corpus_labels.append(f"[fact/{category} #{fid}] {content}")
    for did, decision, rationale in decision_rows:
        text = f"{decision} {rationale or ''}"
        corpus_texts.append(text)
        corpus_labels.append(f"[decision #{did}] {decision}" + (f" — {rationale}" if rationale else ""))
    for pid, pattern, note in pattern_rows:
        text = f"{pattern} {note or ''}"
        corpus_texts.append(text)
        corpus_labels.append(f"[code_pattern #{pid}] {pattern}" + (f" ({note})" if note else ""))

    if not corpus_texts:
        return "No facts, decisions, or code patterns recorded yet to search."

    docs = [_tokenize(t) for t in corpus_texts]
    vectors, idf = _tfidf_vectors(docs)

    q_tokens = _tokenize(query)
    q_tf = Counter(q_tokens)
    q_total = sum(q_tf.values()) or 1
    q_vector = {term: (count / q_total) * idf.get(term, 0.0) for term, count in q_tf.items()}

    scored = sorted(
        ((score, label) for score, label in
         ((_cosine(q_vector, vec), label) for vec, label in zip(vectors, corpus_labels))),
        key=lambda pair: pair[0],
        reverse=True,
    )
    top = [(score, label) for score, label in scored if score > 0.05][:limit]
    if not top:
        return f"No memories semantically close to {query!r}."

    lines = [f"{label} (relevance {score:.2f})" for score, label in top]
    return "\n".join(lines)[:MAX_RESULT_CHARS]
