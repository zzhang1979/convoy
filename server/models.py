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
