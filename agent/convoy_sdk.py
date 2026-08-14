"""Convoy Python SDK — for Hermes profiles, OpenClaw agents, or any Python agent.

Example:
    from convoy_sdk import ConvoyAgent

    agent = ConvoyAgent("http://192.168.0.154:8000", "jean", secret="...")
    agent.heartbeat()
    agent.report("task-1", "progress", {"note": "50% done"})
    agent.kv_set("task:task-1", "wip_context", {"done": ["x"], "next": ["y"]})
    agent.handoff("task-1", "michelle", "Handing off, see KV for context")
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

import requests


class ConvoyAgent:
    """A Convoy agent client: register, report events, KV, handoffs, SOP."""

    def __init__(self, server: str, agent_id: str, secret: Optional[str] = None,
                 name: Optional[str] = None, capabilities: Optional[list[str]] = None,
                 endpoint: Optional[str] = None, role: Optional[str] = None):
        self.server = server.rstrip("/")
        self.agent_id = agent_id
        self.secret = secret
        self.name = name or agent_id
        self.capabilities = capabilities or ["shell", "web"]
        self.endpoint = endpoint
        self.role = role
        self.sop: list[dict] = []
        self.wip_handoffs: list[dict] = []
        if not self.secret:
            self.register()

    # --- lifecycle ---------------------------------------------------------

    def register(self) -> dict:
        """Join Convoy; stores secret + onboarding SOP/WIP."""
        body: dict[str, Any] = {
            "agent_id": self.agent_id, "name": self.name,
            "capabilities": self.capabilities, "endpoint": self.endpoint,
        }
        if self.role:
            body["role"] = self.role
        r = requests.post(f"{self.server}/api/register", json=body, timeout=15)
        r.raise_for_status()
        d = r.json()
        self.secret = d["secret"]
        self.sop = d.get("sop", [])
        self.wip_handoffs = d.get("wip_handoffs", [])
        return d

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.secret}"}

    # --- events ------------------------------------------------------------

    def event(self, type_: str, task_id: Optional[str] = None,
              payload: Optional[dict] = None) -> dict:
        """Append an event (idempotent — generates event_id)."""
        body = {
            "event_id": uuid.uuid4().hex,
            "type": type_,
            "payload": payload or {},
        }
        if task_id:
            body["task_id"] = task_id
        r = requests.post(f"{self.server}/api/events", json=body,
                          headers=self._auth(), timeout=15)
        r.raise_for_status()
        return r.json()

    def heartbeat(self) -> dict:
        return self.event("heartbeat")

    def report(self, task_id: str, note: str, pct: Optional[int] = None) -> dict:
        """Convenience: report progress on a task."""
        payload: dict[str, Any] = {"note": note}
        if pct is not None:
            payload["pct"] = pct
        return self.event("progress", task_id, payload)

    def done(self, task_id: str, summary: str, artifacts: Optional[list[str]] = None) -> dict:
        """Mark a task done (with artifacts — 'done' means artifacts exist)."""
        payload: dict[str, Any] = {"summary": summary}
        for url in artifacts or []:
            self.event("artifact_published", task_id, {"url": url, "kind": "artifact"})
        return self.event("done", task_id, payload)

    def blocked(self, task_id: str, reason: str) -> dict:
        return self.event("blocked_on", task_id, {"reason": reason})

    # --- KV store (S2.1) ---------------------------------------------------

    def kv_set(self, namespace: str, key: str, value: Any) -> dict:
        r = requests.put(f"{self.server}/api/kv/{namespace}/{key}",
                         json={"key": key, "value": value},
                         headers=self._auth(), timeout=15)
        r.raise_for_status()
        return r.json()

    def kv_get(self, namespace: str, key: str) -> Optional[dict]:
        r = requests.get(f"{self.server}/api/kv/{namespace}/{key}",
                         headers=self._auth(), timeout=15)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def kv_list(self, namespace: str, prefix: str = "") -> list[dict]:
        r = requests.get(f"{self.server}/api/kv/{namespace}",
                         params={"prefix": prefix}, headers=self._auth(), timeout=15)
        r.raise_for_status()
        return r.json().get("items", [])

    # --- handoffs (S2.2) ---------------------------------------------------

    def handoff(self, task_id: str, to_agent: str, notes: str) -> dict:
        """Hand a WIP task to another agent (SOP: write wip_context KV first)."""
        return requests.post(
            f"{self.server}/api/tasks/{task_id}/handoff",
            json={"to_agent": to_agent, "notes": notes},
            headers=self._auth(), timeout=15,
        ).json()

    def accept_handoff(self, handoff_id: int) -> dict:
        return requests.post(
            f"{self.server}/api/handoffs/{handoff_id}/accept",
            headers=self._auth(), timeout=15,
        ).json()

    def my_handoffs(self) -> list[dict]:
        return requests.get(f"{self.server}/api/handoffs",
                            headers=self._auth(), timeout=15).json().get("handoffs", [])

    # --- SOP (S2.3) --------------------------------------------------------

    def get_sop(self) -> list[dict]:
        r = requests.get(f"{self.server}/api/sop", headers=self._auth(), timeout=15)
        r.raise_for_status()
        self.sop = r.json().get("sop", [])
        return self.sop

    # --- token usage (S4.1) ------------------------------------------------

    def report_usage(self, tokens_in: int, tokens_out: int, model: str = "unknown",
                     task_id: Optional[str] = None) -> dict:
        """Self-report LLM token usage after a call (one line per call)."""
        r = requests.post(f"{self.server}/api/usage",
                          json={"tokens_in": tokens_in, "tokens_out": tokens_out,
                                "model": model, "task_id": task_id},
                          headers=self._auth(), timeout=15)
        r.raise_for_status()
        return r.json()


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Convoy agent CLI: join + heartbeat")
    p.add_argument("--server", default="http://localhost:8000",
                   help="Convoy server URL (default: http://localhost:8000)")
    p.add_argument("--agent", default="sdk-test", help="agent id (default: sdk-test)")
    p.add_argument("--role", default=None,
                   help="role: engineer|designer|qa|analyst (auto-creates schedule)")
    p.add_argument("--name", default=None, help="display name (default: agent id)")
    args = p.parse_args()

    a = ConvoyAgent(args.server, args.agent, role=args.role, name=args.name)
    print(f"registered {args.agent} role={args.role} - sop rules: {len(a.sop)}")
    a.heartbeat()
    print("heartbeat ok")
