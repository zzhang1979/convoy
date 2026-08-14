"""Convoy SQLite data model — append-only event log + agent registry.

S1.1: schema for the two core tables plus connection helpers.
The DB path is taken from the CONVOY_DB env var (default: <repo>/convoy.db)
so tests can point at a throwaway file.
"""

from __future__ import annotations

import os
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
    return p if p.is_absolute() else DEFAULT_DB.parent / p


def connect(db: Path | None = None) -> sqlite3.Connection:
    """Open a connection with sane defaults; callers own the lifecycle."""
    path = db or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
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
    append raises sqlite3.IntegrityError here, which the API layer maps to a
    quiet 202 (already recorded).
    """
    cur = conn.execute(
        """
        INSERT INTO events (event_id, agent_id, task_id, type, payload)
        VALUES (?, ?, ?, ?, ?)
        """,
        (event_id, agent_id, task_id, type_, __import__("json").dumps(payload)),
    )
    conn.commit()
    return cur.rowcount == 1
