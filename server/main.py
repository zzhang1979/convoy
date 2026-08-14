"""Convoy — agent orchestration & work tracking server.

Tiny, boring core: append-only event log + REST intake + derived views.
Per co-design: facts not states; status is a query (see derive.py).
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from derive import derive_board, derive_tasks

DB_PATH = os.environ.get("CONVOY_DB", "convoy.db")
COMMANDER_TOKEN = os.environ.get("CONVOY_COMMANDER_TOKEN", "commander-secret")

app = FastAPI(title="Convoy", version="0.1.0")


# ---------- persistence ----------

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id    TEXT NOT NULL UNIQUE,
                agent_id    TEXT NOT NULL,
                task_id     TEXT,
                type        TEXT NOT NULL,
                payload     TEXT NOT NULL DEFAULT '{}',
                received_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS agents (
                agent_id        TEXT PRIMARY KEY,
                name            TEXT,
                secret          TEXT NOT NULL,
                capabilities    TEXT NOT NULL DEFAULT '[]',
                endpoint        TEXT,
                joined_at       TEXT NOT NULL DEFAULT (datetime('now')),
                last_heartbeat  TEXT
            );
            """
        )


init_db()


# ---------- models ----------

class RegisterIn(BaseModel):
    agent_id: str = Field(min_length=1, max_length=64)
    name: Optional[str] = None
    capabilities: List[str] = []
    endpoint: Optional[str] = None


class EventIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)
    task_id: Optional[str] = None
    type: str = Field(pattern="^(created|started|blocked_on|unblocked|progress|artifact_published|done|cancelled|heartbeat)$")
    payload: Dict[str, Any] = {}


# ---------- auth helpers ----------

def agent_from_token(authorization: Optional[str]) -> sqlite3.Row:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    with db() as conn:
        row = conn.execute("SELECT * FROM agents WHERE secret = ?", (token,)).fetchone()
    if not row:
        raise HTTPException(401, "Unknown agent secret")
    return row


def commander_from_token(authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    if authorization.removeprefix("Bearer ").strip() != COMMANDER_TOKEN:
        raise HTTPException(403, "Commander token required")


# ---------- API ----------

@app.get("/api/health")
def health():
    with db() as conn:
        ev_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    return {"status": "ok", "events": ev_count}


@app.post("/api/register", status_code=201)
def register(body: RegisterIn):
    secret = uuid.uuid4().hex
    with db() as conn:
        try:
            conn.execute(
                "INSERT INTO agents (agent_id, name, secret, capabilities, endpoint) VALUES (?,?,?,?,?)",
                (body.agent_id, body.name or body.agent_id, secret,
                 json.dumps(body.capabilities), body.endpoint),
            )
        except sqlite3.IntegrityError:
            # agent exists — issue a NEW secret (rotation)
            conn.execute("UPDATE agents SET secret = ? WHERE agent_id = ?", (secret, body.agent_id))
    return {"agent_id": body.agent_id, "secret": secret}


@app.post("/api/events", status_code=202)
def post_event(body: EventIn, authorization: Optional[str] = Header(None)):
    agent = agent_from_token(authorization)
    now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO events (event_id, agent_id, task_id, type, payload, received_at) VALUES (?,?,?,?,?,?)",
                (body.event_id, agent["agent_id"], body.task_id, body.type,
                 json.dumps(body.payload), now),
            )
            if body.type == "heartbeat":
                conn.execute("UPDATE agents SET last_heartbeat = ? WHERE agent_id = ?", (now, agent["agent_id"]))
    except sqlite3.IntegrityError:
        return JSONResponse({"status": "duplicate", "event_id": body.event_id}, status_code=202)
    return {"status": "accepted", "event_id": body.event_id}


@app.get("/api/board")
def board(authorization: Optional[str] = Header(None)):
    commander_from_token(authorization)
    with db() as conn:
        events = []
        for r in conn.execute("SELECT * FROM events ORDER BY id").fetchall():
            d = dict(r)
            try:
                d["payload"] = json.loads(d["payload"])
            except (json.JSONDecodeError, TypeError):
                d["payload"] = {}
            events.append(d)
        agents = [dict(r) for r in conn.execute("SELECT agent_id, name, capabilities, last_heartbeat FROM agents").fetchall()]
    b = derive_board(events)
    return {"board": b, "agents": agents}


@app.get("/api/tasks/{task_id}")
def task_detail(task_id: str, authorization: Optional[str] = Header(None)):
    commander_from_token(authorization)
    with db() as conn:
        events = []
        for r in conn.execute(
                "SELECT * FROM events WHERE task_id = ? ORDER BY id", (task_id,)).fetchall():
            d = dict(r)
            try:
                d["payload"] = json.loads(d["payload"])
            except (json.JSONDecodeError, TypeError):
                d["payload"] = {}
            events.append(d)
    proj = derive_tasks(events).get(task_id)
    return {"task_id": task_id, "events": events, "projection": proj.to_dict() if proj else None}


@app.get("/api/agents")
def agents_list(authorization: Optional[str] = Header(None)):
    commander_from_token(authorization)
    with db() as conn:
        agents = [dict(r) for r in conn.execute("SELECT agent_id, name, capabilities, endpoint, joined_at, last_heartbeat FROM agents").fetchall()]
    return {"agents": agents}
