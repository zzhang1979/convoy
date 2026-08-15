"""Convoy — status derivation module.

Derives task/agent status from the append-only event log.
Status is a QUERY, never stored state (per co-design with Jasmine + Michelle).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Status vocabulary: todo / doing / review / done / stuck / cancelled
HEARTBEAT_STALE_SECONDS = 300  # agent marked stale after 5 min no heartbeat


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


class TaskProjection:
    """One task's derived state, rebuilt from its event sequence."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.title = ""
        self.assignee = None
        self.project = None
        self.created_at: Optional[str] = None
        self.last_event_at: Optional[str] = None
        self.latest_type: Optional[str] = None
        self.block_reason: Optional[str] = None
        self.artifacts: List[Dict[str, Any]] = []
        self.heartbeat_at: Optional[str] = None
        self.summary: Optional[str] = None
        self.roles: Dict[str, str] = {}   # agent_id -> role snapshot (W4)

    def apply(self, ev: Dict[str, Any]) -> None:
        typ = ev.get("type", "")
        payload = ev.get("payload") or {}
        self.last_event_at = ev.get("received_at") or ev.get("created_at")
        self.latest_type = typ
        if typ == "created":
            self.title = payload.get("title", self.title)
            self.assignee = payload.get("assignee", self.assignee)
            self.project = payload.get("project", self.project)
            if not self.created_at:
                self.created_at = self.last_event_at
        elif typ == "blocked_on":
            self.block_reason = payload.get("reason", "blocked")
        elif typ == "unblocked":
            self.block_reason = None
        elif typ == "artifact_published":
            self.artifacts.append({"url": payload.get("url"), "kind": payload.get("kind")})
        elif typ == "done":
            self.summary = payload.get("summary", "")
        elif typ == "heartbeat":
            self.heartbeat_at = self.last_event_at
        # W4: snapshot role for the agent at event time (role stored in payload)
        if ev.get("agent_id"):
            role = (ev.get("payload") or {}).get("role") or ev.get("role")
            if role:
                self.roles[ev["agent_id"]] = role

    def status(self, now: Optional[str] = None) -> str:
        """Derive status from facts. Order matters."""
        now = now or utcnow()
        # done iff artifacts exist or done event (latest terminal fact)
        if self.latest_type == "done":
            return "done"
        if self.artifacts:
            return "review"
        # stuck iff latest fact is blocked_on (no unblocked after)
        if self.latest_type == "blocked_on" or self.block_reason is not None:
            return "stuck"
        # doing iff started work (has any event after created) and recent heartbeat
        if self.latest_type and self.latest_type != "created":
            if self.heartbeat_at:
                hb = parse_time(self.heartbeat_at)
                if (parse_time(now) - hb).total_seconds() < HEARTBEAT_STALE_SECONDS:
                    return "doing"
                return "stale"  # heartbeat expired — agent went quiet
            return "doing"
        return "todo"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "assignee": self.assignee,
            "project": self.project,
            "status": self.status(),
            "block_reason": self.block_reason,
            "artifacts": self.artifacts,
            "created_at": self.created_at,
            "last_event_at": self.last_event_at,
            "summary": self.summary,
            "roles": self.roles,
        }


def derive_tasks(events: List[Dict[str, Any]]) -> Dict[str, TaskProjection]:
    """Group events by task_id and replay each task's projection."""
    tasks: Dict[str, TaskProjection] = {}
    for ev in sorted(events, key=lambda e: e.get("received_at") or ""):
        tid = ev.get("task_id")
        if not tid:
            continue
        proj = tasks.setdefault(tid, TaskProjection(tid))
        proj.apply(ev)
    return tasks


def derive_board(events: List[Dict[str, Any]], project: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Pulse board: running / stuck / done-today / todo. Optionally filter by project (W2)."""
    tasks = derive_tasks(events)
    board = {"running": [], "stuck": [], "done_today": [], "todo": [], "stale": []}
    today_start = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    for proj in tasks.values():
        d = proj.to_dict()
        if project and (d.get("project") or "") != project:
            continue
        st = d["status"]
        if st == "done":
            board["done_today"].append(d)
        elif st == "stuck":
            board["stuck"].append(d)
        elif st == "stale":
            board["stale"].append(d)
        elif st == "doing":
            board["running"].append(d)
        else:
            board["todo"].append(d)
    for key in board:
        board[key].sort(key=lambda t: t.get("last_event_at") or "")
    return board
