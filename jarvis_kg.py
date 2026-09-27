"""Lite knowledge graph (2026-09-27, feature batch C5): people, projects, tasks, meetings and files as
SQLite nodes and edges. No graph database, no model call.

`kg_nodes(id, type, name, key UNIQUE, meta_json)` and `kg_edges(from_id, to_id, rel, meta_json)`.
`sync()` (every SYNC_MIN minutes from the scheduler, cheap SQL) derives stable identities from tables
Jarvis already has:
  person   relationship facts that carry an email address (key = the address)
  project  autonomy_projects
  task     open/done commitments (edge to its project; edge to the person whose address sent it)
  meeting  meetings (edge to their action-item tasks isn't tracked: they go through commitments)
Users (and the model, attended only) can add their own edges: "Sam works on Apollo".
`query(name, depth<=2)` finds matching nodes and walks their edges.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime

SYNC_MIN = 30
TYPES = ("person", "project", "task", "meeting", "file", "thing")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def ensure(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS kg_nodes (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL, "
                 "name TEXT NOT NULL, key TEXT NOT NULL UNIQUE, meta_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS kg_edges (from_id INTEGER NOT NULL, to_id INTEGER NOT NULL, rel TEXT NOT NULL, "
                 "meta_json TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (from_id, to_id, rel))")


def _exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def upsert_node(conn, ntype: str, name: str, key: str, meta: dict | None = None) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute("INSERT INTO kg_nodes (type, name, key, meta_json, updated_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(key) "
                 "DO UPDATE SET name=excluded.name, meta_json=excluded.meta_json, updated_at=excluded.updated_at",
                 (ntype, name[:120], key[:200], json.dumps(meta or {}), now))
    return conn.execute("SELECT id FROM kg_nodes WHERE key=?", (key[:200],)).fetchone()[0]


def add_edge(conn, a: int, b: int, rel: str) -> None:
    conn.execute("INSERT OR IGNORE INTO kg_edges (from_id, to_id, rel) VALUES (?, ?, ?)", (a, b, rel[:40]))


def _person_name(fact: str, email: str) -> str:
    before = fact.split(email)[0]
    m = re.search(r"([A-Z][a-z]+(?: [A-Z][a-z]+)?)(?:'s)?\s*(?:email|address|is|,|:|-|\(|$)", before)
    return m.group(1) if m else email.split("@")[0]


def sync(connect, lock) -> dict:
    counts = {"person": 0, "project": 0, "task": 0, "meeting": 0}
    with lock:
        conn = connect()
        try:
            ensure(conn)
            people: dict[str, int] = {}
            if _exists(conn, "memory_facts"):
                for (content,) in conn.execute("SELECT content FROM memory_facts WHERE category='relationship' "
                                               "AND superseded_at IS NULL"):
                    for email in _EMAIL_RE.findall(content or ""):
                        email = email.lower().rstrip(".")
                        people[email] = upsert_node(conn, "person", _person_name(content, email), f"person:{email}",
                                                    {"email": email, "fact": content[:200]})
                        counts["person"] += 1
            projects: dict[int, int] = {}
            if _exists(conn, "autonomy_projects"):
                for row in conn.execute("SELECT id, name, status FROM autonomy_projects"):
                    projects[row[0]] = upsert_node(conn, "project", row[1], f"project:{row[0]}", {"status": row[2]})
                    counts["project"] += 1
            if _exists(conn, "commitments"):
                for cid, desc, status, pid, meta, deadline in conn.execute(
                        "SELECT id, description, status, related_project_id, metadata_json, deadline_iso FROM commitments "
                        "WHERE quarantined=0 ORDER BY id DESC LIMIT 500"):
                    tid = upsert_node(conn, "task", desc or f"task {cid}", f"task:{cid}",
                                      {"status": status, "deadline": deadline})
                    counts["task"] += 1
                    if pid in projects:
                        add_edge(conn, tid, projects[pid], "part_of")
                    sender = str((json.loads(meta or "{}") if meta else {}).get("sender") or "").lower()
                    for email in _EMAIL_RE.findall(sender):
                        if email in people:
                            add_edge(conn, people[email], tid, "asked_for")
            if _exists(conn, "meetings"):
                for mid, title, started in conn.execute("SELECT id, title, started_at FROM meetings ORDER BY id DESC LIMIT 200"):
                    upsert_node(conn, "meeting", title or "Meeting", f"meeting:{mid}", {"started": started})
                    counts["meeting"] += 1
            # Derived nodes whose source is gone (forgotten fact, pruned commitment, deleted meeting) go too.
            live = {f"person:{e}" for e in people}
            if _exists(conn, "commitments"):
                live |= {f"task:{r[0]}" for r in conn.execute("SELECT id FROM commitments WHERE quarantined=0")}
            if _exists(conn, "meetings"):
                live |= {f"meeting:{r[0]}" for r in conn.execute("SELECT id FROM meetings")}
            if _exists(conn, "autonomy_projects"):
                live |= {f"project:{r[0]}" for r in conn.execute("SELECT id FROM autonomy_projects")}
            stale = [nid for nid, key in conn.execute("SELECT id, key FROM kg_nodes WHERE key GLOB "
                                                      "'person:*' OR key GLOB 'task:*' OR key GLOB 'meeting:*' "
                                                      "OR key GLOB 'project:*'") if key not in live]
            for nid in stale:
                conn.execute("DELETE FROM kg_edges WHERE from_id=? OR to_id=?", (nid, nid))
                conn.execute("DELETE FROM kg_nodes WHERE id=?", (nid,))
            conn.commit()
        finally:
            conn.close()
    return counts


def relate(connect, lock, a: str, rel: str, b: str, a_type: str = "thing", b_type: str = "thing") -> str:
    """A user-stated relation, e.g. ("Sam", "works_on", "Apollo"). Reuses existing nodes by name."""
    a, b, rel = (a or "").strip(), (b or "").strip(), re.sub(r"\W+", "_", (rel or "").strip().lower())[:40]
    if not a or not b or not rel:
        return "Say who/what, the relation, and to whom/what."
    with lock:
        conn = connect()
        try:
            ensure(conn)
            ids = []
            for name, t in ((a, a_type), (b, b_type)):
                row = conn.execute("SELECT id FROM kg_nodes WHERE lower(name)=lower(?) ORDER BY id LIMIT 1", (name,)).fetchone()
                ids.append(row[0] if row else upsert_node(conn, t if t in TYPES else "thing", name,
                                                          f"user:{t}:{name.lower()}"))
            add_edge(conn, ids[0], ids[1], rel)
            conn.commit()
        finally:
            conn.close()
    return f"Noted: {a} {rel.replace('_', ' ')} {b}."


def query(connect, lock, name: str, depth: int = 2, limit: int = 40) -> dict:
    depth = max(1, min(int(depth or 2), 2))
    with lock:
        conn = connect()
        try:
            ensure(conn)
            conn.row_factory = sqlite3.Row
            starts = [dict(r) for r in conn.execute("SELECT * FROM kg_nodes WHERE name LIKE ? ORDER BY length(name) LIMIT 5",
                                                    (f"%{(name or '').strip()}%",))] if (name or "").strip() else []
            frontier, seen, edges = {s["id"] for s in starts}, {s["id"] for s in starts}, []
            for _ in range(depth):
                if not frontier:
                    break
                marks = ",".join("?" * len(frontier))
                rows = conn.execute(f"SELECT e.from_id, e.to_id, e.rel, a.name AS a, a.type AS at, b.name AS b, b.type AS bt "
                                    f"FROM kg_edges e JOIN kg_nodes a ON a.id=e.from_id JOIN kg_nodes b ON b.id=e.to_id "
                                    f"WHERE e.from_id IN ({marks}) OR e.to_id IN ({marks}) LIMIT ?",
                                    (*frontier, *frontier, limit)).fetchall()
                nxt = set()
                for r in rows:
                    edges.append(dict(r))
                    for nid in (r["from_id"], r["to_id"]):
                        if nid not in seen:
                            seen.add(nid)
                            nxt.add(nid)
                frontier = nxt
        finally:
            conn.close()
    uniq = list({(e["from_id"], e["to_id"], e["rel"]): e for e in edges}.values())[:limit]
    return {"matches": starts, "edges": uniq}


def format_query(r: dict) -> str:
    if not r["matches"]:
        return "I don't have anything by that name in the graph."
    head = ", ".join(f"{m['name']} ({m['type']})" for m in r["matches"])
    if not r["edges"]:
        return f"Found {head}, but nothing is linked to it yet."
    return f"Found {head}. Links:\n" + "\n".join(
        f"- {e['a']} ({e['at']}) {e['rel'].replace('_', ' ')} {e['b']} ({e['bt']})" for e in r["edges"])
