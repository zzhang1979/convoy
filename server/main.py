"""Convoy server — FastAPI application (S1.1 skeleton + S1.2 intake API).

Run:  uvicorn server.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Any, Literal, Optional

from fastapi import FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import models
from .derive import derive_board, derive_tasks

# --- request/response models -----------------------------------------------

EventType = Literal[
    "created", "started", "blocked_on", "unblocked", "artifact_published",
    "progress", "heartbeat", "done", "cancelled",
]


class RegisterRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    name: Optional[str] = None
    capabilities: list[str] = []
    endpoint: Optional[str] = None


class RegisterResponse(BaseModel):
    agent_id: str
    secret: str


class EventRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    task_id: Optional[str] = None
    type: EventType
    payload: dict[str, Any] = {}


# --- app -------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_: FastAPI):
    models.init_db()
    yield


app = FastAPI(title="Convoy", version="0.1.0", lifespan=lifespan)

# Dev-friendly CORS so Jasmine's pulse UI (S1.6) can fetch the API
# from a different origin during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _authorize(authorization: Optional[str]) -> str:
    """Validate `Authorization: Bearer <secret>`; return the agent_id."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    agent_id = models.agent_id_for_secret(token)
    if agent_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid bearer token")
    return agent_id


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Liveness probe (open)."""
    try:
        with models.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        db_status = "ok"
    except Exception:
        db_status = "error"
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "service": "convoy",
        "version": app.version,
        "db": db_status,
    }


@app.post("/api/register", response_model=RegisterResponse)
def register(req: RegisterRequest, response: Response) -> RegisterResponse:
    """Agent onboarding (open, one-time). 201 on fresh join, 200 on re-join.

    Idempotent: re-registering an existing agent_id returns the same
    secret instead of failing or minting a new one.
    """
    secret, created = models.register_agent(
        req.agent_id, req.name, req.capabilities, req.endpoint
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return RegisterResponse(agent_id=req.agent_id, secret=secret)


@app.post("/api/events", status_code=status.HTTP_202_ACCEPTED)
def append_event(req: EventRequest,
                 authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    """Append an event to the log (bearer-auth required).

    Idempotent: retrying with the same event_id returns 202 with
    ``"status": "duplicate"`` and does not create a second row.
    """
    agent_id = _authorize(authorization)
    inserted = models.append_event(
        agent_id, req.event_id, req.task_id, req.type, req.payload
    )
    if req.type == "heartbeat":
        models.touch_heartbeat(agent_id)
    return {
        "event_id": req.event_id,
        "status": "accepted" if inserted else "duplicate",
    }


# --- commander views (derived from the event log) --------------------------

def _commander(authorization: str | None) -> None:
    """Validate commander token for read endpoints."""
    expected = os.environ.get("CONVOY_COMMANDER_TOKEN", "commander-secret")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    if authorization.removeprefix("Bearer ").strip() != expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "commander token required")


def _load_events() -> list[dict[str, Any]]:
    """Read all events (payloads parsed) for projection."""
    events: list[dict[str, Any]] = []
    with models.connect() as conn:
        rows = conn.execute("SELECT * FROM events ORDER BY id").fetchall()
    for r in rows:
        d = dict(r)
        try:
            d["payload"] = json.loads(d["payload"])
        except (json.JSONDecodeError, TypeError):
            d["payload"] = {}
        events.append(d)
    return events


@app.get("/api/board")
def board(authorization: str | None = Header(None)) -> dict[str, Any]:
    """Commander pulse: running / stuck / done-today / todo (derived)."""
    _commander(authorization)
    events = _load_events()
    b = derive_board(events)
    with models.connect() as conn:
        agents = [
            dict(r) for r in conn.execute(
                "SELECT agent_id, name, capabilities, last_heartbeat FROM agents"
            ).fetchall()
        ]
    return {"board": b, "agents": agents}


@app.get("/api/tasks/{task_id}")
def task_detail(task_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    """Task timeline + derived projection."""
    _commander(authorization)
    events = [e for e in _load_events() if e.get("task_id") == task_id]
    proj = derive_tasks(events).get(task_id)
    return {"task_id": task_id, "events": events, "projection": proj.to_dict() if proj else None}


@app.get("/api/agents")
def agents_list(authorization: str | None = Header(None)) -> dict[str, Any]:
    """Agent registry with heartbeat status."""
    _commander(authorization)
    with models.connect() as conn:
        agents = [
            dict(r) for r in conn.execute(
                "SELECT agent_id, name, capabilities, endpoint, joined_at, last_heartbeat FROM agents"
            ).fetchall()
        ]
    return {"agents": agents}
