"""Convoy server — FastAPI application (S1.1 skeleton + S1.2 intake API).

Run:  uvicorn server.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import models
from .derive import derive_board, derive_tasks

# --- request/response models -----------------------------------------------

EventType = Literal[
    "created", "started", "blocked_on", "unblocked", "artifact_published",
    "progress", "heartbeat", "done", "cancelled", "handoff_requested",
    "handoff_accepted",
]


class RegisterRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    name: Optional[str] = None
    capabilities: list[str] = []
    endpoint: Optional[str] = None
    role: Optional[str] = None


class RegisterResponse(BaseModel):
    agent_id: str
    secret: str
    sop: list[dict[str, Any]] = []
    wip_handoffs: list[dict[str, Any]] = []


class EventRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    task_id: Optional[str] = None
    type: EventType
    payload: dict[str, Any] = {}


# --- app -------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_: FastAPI):
    models.init_db()
    models.seed_sop()
    models.seed_roles()
    yield


app = FastAPI(title="Convoy", version="0.1.0", lifespan=lifespan)

# Serve the commander pulse UI at /ui/ and /
UI_DIR = Path(__file__).resolve().parent.parent / "ui"
app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")


@app.get("/")
def index() -> FileResponse:
    """Commander UI at the root."""
    return FileResponse(UI_DIR / "index.html")

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
    # Auto-create schedule with role (defaults to 09:00-17:00 AEST)
    models.schedule_set(req.agent_id, role_name=req.role)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    # Onboarding payload: SOP + any WIP assigned to this agent
    sop = models.sop_list()
    handoffs = models.handoff_list(agent_id=req.agent_id)
    wip = [
        h for h in handoffs
        if h["status"] == "requested" and h["to_agent"] == req.agent_id
    ]
    return RegisterResponse(
        agent_id=req.agent_id,
        secret=secret,
        sop=sop,
        wip_handoffs=wip,
    )


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


# --- KV store (S2.1) -------------------------------------------------------

class KvSetRequest(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    value: Any


@app.put("/api/kv/{namespace}/{key}")
def kv_put(namespace: str, key: str, body: KvSetRequest,
           authorization: str | None = Header(None)) -> dict[str, Any]:
    """Upsert a KV pair. Agent-scoped: namespace must be task:<id> or agent:<self>."""
    agent_id = _authorize(authorization)
    value = body.value
    # Scope check: agents may only write their own namespace or a task namespace
    if not (namespace.startswith("task:") or namespace == f"agent:{agent_id}"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "namespace must be task:<id> or agent:<your_id>")
    models.kv_set(namespace, key, value, agent_id)
    return {"namespace": namespace, "key": key, "status": "set"}


@app.get("/api/kv/{namespace}/{key}")
def kv_get(namespace: str, key: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    """Read a KV pair."""
    _authorize(authorization)
    pair = models.kv_get(namespace, key)
    if pair is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "key not found")
    return pair


@app.get("/api/kv/{namespace}")
def kv_list(namespace: str, prefix: str = "", authorization: str | None = Header(None)) -> dict[str, Any]:
    """List KV pairs in a namespace, optionally filtered by key prefix."""
    _authorize(authorization)
    pairs = models.kv_list(namespace, prefix)
    return {"namespace": namespace, "prefix": prefix, "items": pairs}


@app.delete("/api/kv/{namespace}/{key}")
def kv_delete(namespace: str, key: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    """Delete a KV pair."""
    agent_id = _authorize(authorization)
    if not (namespace.startswith("task:") or namespace == f"agent:{agent_id}"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "namespace must be task:<id> or agent:<your_id>")
    deleted = models.kv_delete(namespace, key)
    return {"namespace": namespace, "key": key, "deleted": deleted}


# --- SOP (S2.3) ------------------------------------------------------------

@app.get("/api/sop")
def sop_get(authorization: str | None = Header(None)) -> dict[str, Any]:
    """Return the collaboration SOP (agent auth)."""
    _authorize(authorization)
    return {"sop": models.sop_list()}


# --- Handoffs (S2.2) -------------------------------------------------------

class HandoffRequest(BaseModel):
    to_agent: str
    notes: str = ""


@app.post("/api/tasks/{task_id}/handoff")
def handoff_create(task_id: str, req: HandoffRequest,
                   authorization: str | None = Header(None)) -> dict[str, Any]:
    """Request a handoff of a WIP task to another agent."""
    from_agent = _authorize(authorization)
    # Record handoff + an event so the timeline shows it
    h_id = models.handoff_request(task_id, from_agent, req.to_agent, req.notes)
    models.append_event(
        from_agent, f"handoff-{h_id}", task_id, "handoff_requested",
        {"to_agent": req.to_agent, "notes": req.notes},
    )
    return {"handoff_id": h_id, "task_id": task_id, "status": "requested"}


@app.post("/api/handoffs/{handoff_id}/accept")
def handoff_accept(handoff_id: int, authorization: str | None = Header(None)) -> dict[str, Any]:
    """Accept a handoff (only the to_agent)."""
    agent_id = _authorize(authorization)
    ok = models.handoff_accept(handoff_id, agent_id)
    if not ok:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "not the target agent or handoff not pending")
    return {"handoff_id": handoff_id, "status": "accepted"}


@app.get("/api/handoffs")
def handoffs_list(task_id: str = "", authorization: str | None = Header(None)) -> dict[str, Any]:
    """List handoffs, optionally filtered by task."""
    agent_id = _authorize(authorization)
    items = models.handoff_list(task_id or None, agent_id)
    return {"handoffs": items}


# --- Roles & costing (S3.1) -------------------------------------------------

class RoleSetRequest(BaseModel):
    cost_per_hour: float = Field(ge=0)
    in_cost_per_1m: Optional[float] = Field(default=None, ge=0)
    out_cost_per_1m: Optional[float] = Field(default=None, ge=0)


class TokenCostRequest(BaseModel):
    in_cost_per_1m: float = Field(default=3.0, ge=0)
    out_cost_per_1m: float = Field(default=15.0, ge=0)


@app.put("/api/roles/{role_name}")
def role_put(role_name: str, req: RoleSetRequest,
             authorization: str | None = Header(None)) -> dict[str, Any]:
    """Set a role's cost rate (commander only)."""
    _commander(authorization)
    models.role_set(role_name, req.cost_per_hour)
    return {"role_name": role_name, "cost_per_hour": req.cost_per_hour, "status": "set"}


@app.get("/api/roles")
def roles_get(authorization: str | None = Header(None)) -> dict[str, Any]:
    """List all roles + cost rates."""
    _commander(authorization)
    return {"roles": models.roles_list()}


# --- Schedules / time ranges (S3.2) -----------------------------------------

class ScheduleRequest(BaseModel):
    role_name: Optional[str] = None
    work_start: Optional[str] = None
    work_end: Optional[str] = None
    timezone: Optional[str] = None
    max_hours_per_day: Optional[float] = Field(default=None, ge=0.5, le=24)
    cost_override: Optional[float] = Field(default=None, ge=0)


@app.put("/api/agents/{agent_id}/schedule")
def schedule_put(agent_id: str, req: ScheduleRequest,
                 authorization: str | None = Header(None)) -> dict[str, Any]:
    """Design an agent's working time range (commander only)."""
    _commander(authorization)
    models.schedule_set(
        agent_id, req.role_name, req.work_start, req.work_end,
        req.timezone, req.max_hours_per_day, req.cost_override,
    )
    return {"agent_id": agent_id, "status": "set", **models.schedule_get(agent_id)}


@app.get("/api/agents/{agent_id}/schedule")
def schedule_get(agent_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    """Read an agent's schedule."""
    _commander(authorization)
    return models.schedule_get(agent_id)


# --- Cost calculation (S3.3) -------------------------------------------------

@app.get("/api/costs")
def costs_get(authorization: str | None = Header(None)) -> dict[str, Any]:
    """Cost report: per-agent active hours × role rate, plus role totals."""
    _commander(authorization)
    return models.compute_costs()


# --- Token usage (S4.1-S4.3) -------------------------------------------------

class UsageReportRequest(BaseModel):
    task_id: Optional[str] = None
    model: str = "unknown"
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)


@app.post("/api/usage")
def usage_report(req: UsageReportRequest,
                 authorization: str | None = Header(None)) -> dict[str, Any]:
    """Self-report LLM token usage (agent auth)."""
    agent_id = _authorize(authorization)
    models.usage_report(agent_id, req.task_id, req.model, req.tokens_in, req.tokens_out)
    return {"status": "recorded", "agent_id": agent_id}


@app.get("/api/usage")
def usage_get(agent_id: str = "", task_id: str = "", model: str = "", since: str = "",
              authorization: str | None = Header(None)) -> dict[str, Any]:
    """Usage report with optional filters (commander)."""
    _commander(authorization)
    return models.usage_summary(
        agent_id or None, task_id or None, model or None, since or None
    )


@app.get("/api/costs/full")
def costs_full(authorization: str | None = Header(None)) -> dict[str, Any]:
    """Full cost report: time cost + token cost merged."""
    _commander(authorization)
    return models.usage_merge_costs()


@app.put("/api/roles/{role_name}/token-costs")
def role_token_costs_put(role_name: str, req: TokenCostRequest,
                         authorization: str | None = Header(None)) -> dict[str, Any]:
    """Set a role's token pricing (commander). Body: {in_cost_per_1m, out_cost_per_1m}."""
    _commander(authorization)
    models.role_set_token_costs(role_name, req.in_cost_per_1m, req.out_cost_per_1m)
    return {"role_name": role_name, "in_cost_per_1m": req.in_cost_per_1m,
            "out_cost_per_1m": req.out_cost_per_1m}
