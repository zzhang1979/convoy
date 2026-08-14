"""Convoy SQLite data model — append-only event log + agent registry.

S1.1: schema for the two core tables plus connection helpers.
The DB path is taken from the CONVOY_DB env var (default: <repo>/convoy.db)
so tests can point at a throwaway file.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).resolve().parent.parent / "convoy.db"

# Per docs/technical-design.md — `events` is append-only and the source of
# truth; `agents` holds per-agent secrets for auth on POST /api/events.
SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT NOT NULL UNIQUE,     -- client-supplied dedupe key
    agent_id    TEXT NOT NULL,
    task_id     TEXT,                     -- optional, groups events
    type        TEXT NOT NULL,            -- created|started|blocked_on|unblocked|artifact_published|progress|heartbeat|done|cancelled
    payload     TEXT NOT NULL DEFAULT '{}',  -- JSON: reason, url, note, deps
    received_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agents (
    agent_id        TEXT PRIMARY KEY,
    name            TEXT,
    secret          TEXT NOT NULL,        -- per-agent bearer token
    capabilities    TEXT NOT NULL DEFAULT '[]',  -- JSON array
    endpoint        TEXT,                 -- webhook target (optional)
    joined_at       TEXT NOT NULL DEFAULT (datetime('now')),
    last_heartbeat  TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_id);
CREATE INDEX IF NOT EXISTS idx_events_task  ON events(task_id);
CREATE INDEX IF NOT EXISTS idx_events_type  ON events(type);

CREATE TABLE IF NOT EXISTS kv_store (
    namespace   TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL DEFAULT '{}',  -- JSON value
    updated_by  TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (namespace, key)
);

CREATE TABLE IF NOT EXISTS sop_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_key    TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS handoffs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL,
    from_agent  TEXT NOT NULL,
    to_agent    TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'requested',  -- requested|accepted|declined
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    accepted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_handoffs_task ON handoffs(task_id);
"""


def db_path() -> Path:
    """Resolve the DB file, honoring CONVOY_DB (absolute or repo-relative)."""
    raw = os.environ.get("CONVOY_DB")
    if not raw:
        return DEFAULT_DB
    p = Path(raw)
    return p if p.is_absolute() else (Path(__file__).resolve().parent.parent / p)


def connect(db: Path | None = None) -> sqlite3.Connection:
    """Open a connection (row factory, WAL, FK enforcement)."""
    conn = sqlite3.connect(str(db or db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db: Path | None = None) -> None:
    """Create tables if missing. Safe to call on every startup."""
    conn = connect(db)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def insert_event(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    agent_id: str,
    type_: str,
    payload: dict,
    task_id: str | None = None,
) -> bool:
    """Append an event; returns True if inserted, False if event_id dupes.

    The UNIQUE constraint on event_id is the idempotency backstop — a retried
    append returns False here (API layer maps it to a quiet 202).
    """
    try:
        cur = conn.execute(
            """
            INSERT INTO events (event_id, agent_id, task_id, type, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (event_id, agent_id, task_id, type_, json.dumps(payload)),
        )
        conn.commit()
        return cur.rowcount == 1
    except sqlite3.IntegrityError:
        return False


# ---------- high-level helpers (open a connection per call) ----------

def register_agent(agent_id: str, name: str | None, capabilities: list[str],
                   endpoint: str | None) -> tuple[str, bool]:
    """Create an agent, returning (secret, created).

    Idempotent: re-registering an existing agent_id returns the SAME secret
    (created=False) — no rotation, no surprise key changes.
    """
    conn = connect()
    try:
        existing = conn.execute(
            "SELECT secret FROM agents WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if existing:
            return existing["secret"], False
        secret = secrets.token_hex(32)
        conn.execute(
            "INSERT INTO agents (agent_id, name, secret, capabilities, endpoint) VALUES (?,?,?,?,?)",
            (agent_id, name or agent_id, secret, json.dumps(capabilities), endpoint),
        )
        conn.commit()
        return secret, True
    finally:
        conn.close()


def append_event(agent_id: str, event_id: str, task_id: str | None,
                 type_: str, payload: dict) -> bool:
    """Append an event for an agent; True if inserted, False if duplicate."""
    conn = connect()
    try:
        return insert_event(conn, event_id=event_id, agent_id=agent_id,
                            type_=type_, payload=payload, task_id=task_id)
    finally:
        conn.close()


def agent_id_for_secret(secret: str) -> str | None:
    """Resolve an agent_id from its bearer secret, or None."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT agent_id FROM agents WHERE secret = ?", (secret,)
        ).fetchone()
        return row["agent_id"] if row else None
    finally:
        conn.close()


def touch_heartbeat(agent_id: str, at: str | None = None) -> None:
    """Record the latest heartbeat timestamp for an agent."""
    if at is None:
        import datetime
        at = datetime.datetime.utcnow().isoformat() + "Z"
    conn = connect()
    try:
        conn.execute(
            "UPDATE agents SET last_heartbeat = ? WHERE agent_id = ?",
            (at, agent_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---------- KV store (S2.1) ----------

def kv_set(namespace: str, key: str, value: Any, updated_by: str) -> None:
    """Upsert a key-value pair (JSON value)."""
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO kv_store (namespace, key, value, updated_by, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(namespace, key) DO UPDATE SET
                value = excluded.value,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (namespace, key, json.dumps(value), updated_by),
        )
        conn.commit()
    finally:
        conn.close()


def kv_get(namespace: str, key: str) -> dict | None:
    """Read a KV pair, returning dict or None."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM kv_store WHERE namespace = ? AND key = ?",
            (namespace, key),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["value"] = json.loads(d["value"])
        except (json.JSONDecodeError, TypeError):
            pass
        return d
    finally:
        conn.close()


def kv_list(namespace: str, prefix: str = "") -> list[dict]:
    """List KV pairs in a namespace (optionally by key prefix)."""
    conn = connect()
    try:
        if prefix:
            rows = conn.execute(
                "SELECT * FROM kv_store WHERE namespace = ? AND key LIKE ? ORDER BY key",
                (namespace, prefix + "%"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM kv_store WHERE namespace = ? ORDER BY key",
                (namespace,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["value"] = json.loads(d["value"])
            except (json.JSONDecodeError, TypeError):
                pass
            out.append(d)
        return out
    finally:
        conn.close()


def kv_delete(namespace: str, key: str) -> bool:
    """Delete a KV pair; True if existed."""
    conn = connect()
    try:
        cur = conn.execute(
            "DELETE FROM kv_store WHERE namespace = ? AND key = ?",
            (namespace, key),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------- SOP rules (S2.3) ----------

DEFAULT_SOP: list[dict] = [
    {"rule_key": "sop.register", "title": "Register with capabilities",
     "body": "Join with one command: POST /api/register with agent_id + capabilities. You get a secret; keep it safe.", "priority": 1},
    {"rule_key": "sop.report", "title": "Report via events, never chat",
     "body": "All progress goes through POST /api/events: progress, done, blocked_on, artifact_published. The commander's board derives from events.", "priority": 2},
    {"rule_key": "sop.blocked", "title": "Blockers are flags with reasons",
     "body": "blocked_on event with a reason ('missing token X', 'waiting on review'). Not a status — a fact with context.", "priority": 3},
    {"rule_key": "sop.handoff", "title": "Hand off WIP properly",
     "body": "Before switching tasks: write task:<id>/wip_context KV (what's done, what's next, gotchas), then POST /api/tasks/{id}/handoff to the next agent.", "priority": 4},
    {"rule_key": "sop.pickup", "title": "Pick up WIP from context",
     "body": "New assignee: read task timeline + task:<id>/* KV + handoff notes BEFORE starting. Then accept the handoff.", "priority": 5},
    {"rule_key": "sop.coordination", "title": "Coordinate via events + KV",
     "body": "No side-chat for work state. Decisions, context, and artifacts live in KV + events so any agent can catch up.", "priority": 6},
    {"rule_key": "sop.done", "title": "Done means artifacts exist",
     "body": "A task is done when artifact_published events exist, not when the agent says so.", "priority": 7},
]


def seed_sop() -> None:
    """Insert default SOP rules if missing (idempotent)."""
    conn = connect()
    try:
        for rule in DEFAULT_SOP:
            conn.execute(
                """
                INSERT OR IGNORE INTO sop_rules (rule_key, title, body, priority)
                VALUES (:rule_key, :title, :body, :priority)
                """,
                rule,
            )
        conn.commit()
    finally:
        conn.close()


def sop_list() -> list[dict]:
    """Return all SOP rules ordered by priority."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT rule_key, title, body, priority FROM sop_rules ORDER BY priority"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------- Handoffs (S2.2) ----------

def handoff_request(task_id: str, from_agent: str, to_agent: str, notes: str) -> int:
    """Create a handoff request; returns its id."""
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO handoffs (task_id, from_agent, to_agent, notes) VALUES (?,?,?,?)",
            (task_id, from_agent, to_agent, notes),
        )
        conn.commit()
        rid = cur.lastrowid
        return rid if rid is not None else 0
    finally:
        conn.close()


def handoff_accept(handoff_id: int, agent_id: str) -> bool:
    """Accept a handoff (only the to_agent can). True if accepted."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM handoffs WHERE id = ?", (handoff_id,)
        ).fetchone()
        if not row or row["status"] != "requested":
            return False
        if row["to_agent"] != agent_id:
            return False
        conn.execute(
            "UPDATE handoffs SET status = 'accepted', accepted_at = datetime('now') WHERE id = ?",
            (handoff_id,),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def handoff_list(task_id: str | None = None, agent_id: str | None = None) -> list[dict]:
    """List handoffs, optionally filtered by task or agent."""
    conn = connect()
    try:
        sql = "SELECT * FROM handoffs"
        params: list = []
        clauses = []
        if task_id:
            clauses.append("task_id = ?")
            params.append(task_id)
        if agent_id:
            clauses.append("(from_agent = ? OR to_agent = ?)")
            params += [agent_id, agent_id]
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
