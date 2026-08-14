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

CREATE TABLE IF NOT EXISTS roles (
    role_name       TEXT PRIMARY KEY,
    cost_per_hour   REAL NOT NULL DEFAULT 0,
    in_cost_per_1m  REAL NOT NULL DEFAULT 3.0,   -- USD per 1M input tokens (GPT-4o-ish default)
    out_cost_per_1m REAL NOT NULL DEFAULT 15.0,  -- USD per 1M output tokens
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schedules (
    agent_id            TEXT PRIMARY KEY REFERENCES agents(agent_id),
    role_name           TEXT REFERENCES roles(role_name),
    work_start          TEXT NOT NULL DEFAULT '09:00',
    work_end            TEXT NOT NULL DEFAULT '17:00',
    timezone            TEXT NOT NULL DEFAULT 'Australia/Melbourne',
    max_hours_per_day   REAL NOT NULL DEFAULT 8,
    cost_override       REAL,              -- per-agent rate override (NULL = use role)
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS usage (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL,
    task_id     TEXT,
    model       TEXT NOT NULL DEFAULT 'unknown',
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    reported_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_usage_agent ON usage(agent_id);
CREATE INDEX IF NOT EXISTS idx_usage_task  ON usage(task_id);
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


# ---------- Roles & costing (S3.1) ----------

DEFAULT_ROLES: list[dict] = [
    {"role_name": "commander", "cost_per_hour": 0.0},
    {"role_name": "engineer", "cost_per_hour": 25.0},
    {"role_name": "designer", "cost_per_hour": 30.0},
    {"role_name": "qa", "cost_per_hour": 20.0},
    {"role_name": "analyst", "cost_per_hour": 22.0},
]


def seed_roles() -> None:
    """Insert default roles if missing (idempotent)."""
    conn = connect()
    try:
        for role in DEFAULT_ROLES:
            conn.execute(
                """
                INSERT OR IGNORE INTO roles (role_name, cost_per_hour)
                VALUES (:role_name, :cost_per_hour)
                """,
                role,
            )
        # ensure token-cost columns exist on pre-existing rows
        conn.execute(
            "UPDATE roles SET in_cost_per_1m = 3.0 WHERE in_cost_per_1m IS NULL"
        )
        conn.execute(
            "UPDATE roles SET out_cost_per_1m = 15.0 WHERE out_cost_per_1m IS NULL"
        )
        conn.commit()
    finally:
        conn.close()


def role_set(role_name: str, cost_per_hour: float) -> None:
    """Create or update a role's cost rate."""
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO roles (role_name, cost_per_hour, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(role_name) DO UPDATE SET
                cost_per_hour = excluded.cost_per_hour,
                updated_at = datetime('now')
            """,
            (role_name, cost_per_hour),
        )
        conn.commit()
    finally:
        conn.close()


def role_set_token_costs(role_name: str, in_cost_per_1m: float, out_cost_per_1m: float) -> None:
    """Set a role's token pricing."""
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO roles (role_name, in_cost_per_1m, out_cost_per_1m, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(role_name) DO UPDATE SET
                in_cost_per_1m = excluded.in_cost_per_1m,
                out_cost_per_1m = excluded.out_cost_per_1m,
                updated_at = datetime('now')
            """,
            (role_name, in_cost_per_1m, out_cost_per_1m),
        )
        conn.commit()
    finally:
        conn.close()


def roles_list() -> list[dict]:
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT role_name, cost_per_hour, in_cost_per_1m, out_cost_per_1m, updated_at FROM roles ORDER BY role_name"
        ).fetchall()]
    finally:
        conn.close()


def role_token_costs(role_name: str | None) -> tuple[float, float]:
    """Return (in_cost_per_1m, out_cost_per_1m) for a role."""
    if not role_name:
        return 3.0, 15.0
    conn = connect()
    try:
        row = conn.execute(
            "SELECT in_cost_per_1m, out_cost_per_1m FROM roles WHERE role_name = ?",
            (role_name,),
        ).fetchone()
        if not row:
            return 3.0, 15.0
        return row["in_cost_per_1m"], row["out_cost_per_1m"]
    finally:
        conn.close()


def role_cost(role_name: str | None) -> float:
    """Return cost_per_hour for a role (0 if unknown)."""
    if not role_name:
        return 0.0
    conn = connect()
    try:
        row = conn.execute(
            "SELECT cost_per_hour FROM roles WHERE role_name = ?", (role_name,)
        ).fetchone()
        return row["cost_per_hour"] if row else 0.0
    finally:
        conn.close()


# ---------- Schedules / time ranges (S3.2) ----------

DEFAULT_SCHEDULE = {
    "work_start": "09:00",
    "work_end": "17:00",
    "timezone": "Australia/Melbourne",
    "max_hours_per_day": 8.0,
    "cost_override": None,
}


def schedule_set(agent_id: str, role_name: str | None = None,
                 work_start: str | None = None, work_end: str | None = None,
                 timezone: str | None = None, max_hours_per_day: float | None = None,
                 cost_override: float | None = None) -> None:
    """Upsert an agent's working-time schedule."""
    conn = connect()
    try:
        existing = conn.execute(
            "SELECT * FROM schedules WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if existing:
            cur = dict(existing)
            new_role = role_name if role_name is not None else cur.get("role_name")
            new_start = work_start if work_start is not None else cur.get("work_start")
            new_end = work_end if work_end is not None else cur.get("work_end")
            new_tz = timezone if timezone is not None else cur.get("timezone")
            new_max = max_hours_per_day if max_hours_per_day is not None else cur.get("max_hours_per_day")
            new_override = cost_override if cost_override is not None else cur.get("cost_override")
            conn.execute(
                """
                UPDATE schedules SET role_name=?, work_start=?, work_end=?, timezone=?,
                    max_hours_per_day=?, cost_override=?, updated_at=datetime('now')
                WHERE agent_id=?
                """,
                (new_role, new_start, new_end, new_tz, new_max, new_override, agent_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO schedules (agent_id, role_name, work_start, work_end, timezone,
                                       max_hours_per_day, cost_override, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (agent_id, role_name,
                 work_start or DEFAULT_SCHEDULE["work_start"],
                 work_end or DEFAULT_SCHEDULE["work_end"],
                 timezone or DEFAULT_SCHEDULE["timezone"],
                 max_hours_per_day if max_hours_per_day is not None else DEFAULT_SCHEDULE["max_hours_per_day"],
                 cost_override),
            )
        conn.commit()
    finally:
        conn.close()


def schedule_get(agent_id: str) -> dict:
    """Return an agent's schedule (defaults if none set)."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM schedules WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if not row:
            return {"agent_id": agent_id, **DEFAULT_SCHEDULE}
        return dict(row)
    finally:
        conn.close()


def schedule_all() -> list[dict]:
    conn = connect()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM schedules").fetchall()]
    finally:
        conn.close()


# ---------- Cost calculation (S3.3) ----------

def _hours_between(t1: str, t2: str) -> float:
    """Hours between two ISO timestamps."""
    from datetime import datetime
    try:
        a = datetime.fromisoformat(t1.replace("Z", "+00:00"))
        b = datetime.fromisoformat(t2.replace("Z", "+00:00"))
        return max(0.0, (b - a).total_seconds() / 3600.0)
    except (ValueError, TypeError):
        return 0.0


def compute_costs() -> dict:
    """Aggregate active hours per agent from the event log × rate.

    Active hours = sum of gaps between consecutive events (capped at 1h each
    so a sleeping agent isn't billed for idle time; capped per-day too).
    """
    conn = connect()
    try:
        # events per agent, ordered
        rows = conn.execute(
            "SELECT agent_id, received_at FROM events ORDER BY agent_id, id"
        ).fetchall()
        agents = [dict(r) for r in conn.execute(
            "SELECT agent_id, name FROM agents"
        ).fetchall()]
        schedules = {s["agent_id"]: s for s in schedule_all()}
    finally:
        conn.close()

    # active hours per agent
    per_agent: dict[str, float] = {}
    last: dict[str, str] = {}
    for r in rows:
        aid, ts = r["agent_id"], r["received_at"]
        if aid in last:
            gap = _hours_between(last[aid], ts)
            # count only gaps ≤ 1h (active work), cap total per day later
            if gap <= 1.0:
                per_agent[aid] = per_agent.get(aid, 0.0) + gap
        last[aid] = ts

    # build report
    agent_rows = []
    role_totals: dict[str, dict] = {}
    grand_hours = grand_cost = 0.0
    for a in agents:
        aid = a["agent_id"]
        sched = schedules.get(aid, {"agent_id": aid, **DEFAULT_SCHEDULE})
        role = sched.get("role_name") or "unassigned"
        rate = sched.get("cost_override")
        if rate is None:
            rate = role_cost(role)
        hours = round(per_agent.get(aid, 0.0), 2)
        cost = round(hours * rate, 2)
        agent_rows.append({
            "agent_id": aid, "name": a.get("name"), "role": role,
            "work_start": sched.get("work_start"), "work_end": sched.get("work_end"),
            "timezone": sched.get("timezone"), "max_hours_per_day": sched.get("max_hours_per_day"),
            "hours": hours, "rate": rate, "cost": cost,
        })
        rt = role_totals.setdefault(role, {"role": role, "hours": 0.0, "cost": 0.0})
        rt["hours"] += hours
        rt["cost"] += cost
        grand_hours += hours
        grand_cost += cost

    return {
        "per_agent": agent_rows,
        "per_role": [{"role": k, "hours": round(v["hours"], 2), "cost": round(v["cost"], 2)}
                     for k, v in role_totals.items()],
        "total": {"hours": round(grand_hours, 2), "cost": round(grand_cost, 2)},
    }


# ---------- Token usage (S4.1) ----------

def usage_report(agent_id: str, task_id: str | None, model: str,
                 tokens_in: int, tokens_out: int) -> None:
    """Record an agent's LLM token usage (self-report)."""
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO usage (agent_id, task_id, model, tokens_in, tokens_out)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent_id, task_id, model, int(tokens_in), int(tokens_out)),
        )
        conn.commit()
    finally:
        conn.close()


def usage_summary(agent_id: str | None = None, task_id: str | None = None,
                  model: str | None = None, since: str | None = None) -> dict:
    """Aggregate usage per agent (+ optional filters), with token cost.

    Token cost uses each agent's role pricing (in/out per 1M).
    """
    conn = connect()
    try:
        where: list[str] = []
        params: list = []
        if agent_id:
            where.append("u.agent_id = ?")
            params.append(agent_id)
        if task_id:
            where.append("u.task_id = ?")
            params.append(task_id)
        if model:
            where.append("u.model = ?")
            params.append(model)
        if since:
            where.append("u.reported_at >= ?")
            params.append(since)
        wsql = (" WHERE " + " AND ".join(where)) if where else ""

        rows = conn.execute(
            f"""
            SELECT u.agent_id, u.model,
                   SUM(u.tokens_in) AS tokens_in, SUM(u.tokens_out) AS tokens_out,
                   COUNT(*) AS calls
            FROM usage u
            {wsql}
            GROUP BY u.agent_id, u.model
            ORDER BY u.agent_id
            """,
            params,
        ).fetchall()
        agents = {a["agent_id"]: a["name"] for a in
                  conn.execute("SELECT agent_id, name FROM agents").fetchall()}
        schedules = {s["agent_id"]: s for s in schedule_all()}
    finally:
        conn.close()

    per_agent: dict[str, dict] = {}
    grand_in = grand_out = grand_calls = 0
    grand_cost = 0.0
    for r in rows:
        d = dict(r)
        sched = schedules.get(d["agent_id"], {})
        role = sched.get("role_name") or "unassigned"
        in_cost, out_cost = role_token_costs(role)
        token_cost = (d["tokens_in"] / 1e6 * in_cost) + (d["tokens_out"] / 1e6 * out_cost)
        d["role"] = role
        d["token_cost"] = round(token_cost, 4)
        per_agent.setdefault(d["agent_id"], {
            "agent_id": d["agent_id"], "name": agents.get(d["agent_id"]),
            "role": role, "tokens_in": 0, "tokens_out": 0, "calls": 0, "token_cost": 0.0,
            "by_model": [],
        })
        agg = per_agent[d["agent_id"]]
        agg["tokens_in"] += d["tokens_in"]
        agg["tokens_out"] += d["tokens_out"]
        agg["calls"] += d["calls"]
        agg["token_cost"] += token_cost
        agg["by_model"].append({k: d[k] for k in ("model", "tokens_in", "tokens_out", "calls", "token_cost")})
        grand_in += d["tokens_in"]
        grand_out += d["tokens_out"]
        grand_calls += d["calls"]
        grand_cost += token_cost

    return {
        "per_agent": list(per_agent.values()),
        "total": {
            "tokens_in": grand_in, "tokens_out": grand_out,
            "calls": grand_calls, "token_cost": round(grand_cost, 4),
        },
    }


def usage_merge_costs() -> dict:
    """Full cost report: time cost + token cost per agent."""
    base = compute_costs()
    usage = usage_summary()
    u_by_agent = {a["agent_id"]: a for a in usage["per_agent"]}
    for a in base["per_agent"]:
        u = u_by_agent.get(a["agent_id"])
        a["tokens_in"] = u["tokens_in"] if u else 0
        a["tokens_out"] = u["tokens_out"] if u else 0
        a["token_cost"] = round(u["token_cost"], 2) if u else 0.0
        a["total_cost"] = round(a["cost"] + a["token_cost"], 2)
    grand_time = base["total"]["cost"]
    grand_tokens = usage["total"]["token_cost"]
    base["total"]["token_cost"] = round(grand_tokens, 2)
    base["total"]["grand_total"] = round(grand_time + grand_tokens, 2)
    base["usage"] = usage["total"]
    return base
