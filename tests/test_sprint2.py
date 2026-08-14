"""S2.6 — Sprint 2 integration tests: KV store, SOP, handoffs, OpenClaw adapter.

Covers the collaboration primitives that let a new agent pick up WIP:
  * KV put/get/list (task context)
  * SOP delivery at registration + GET /api/sop
  * Handoff request → WIP visible to new agent → accept → timeline event
  * Namespace permission enforcement
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVOY_DB", str(tmp_path / "convoy_test.db"))
    monkeypatch.setenv("CONVOY_COMMANDER_TOKEN", "test-commander")
    with TestClient(app) as c:
        yield c


def _register(client, agent_id):
    r = client.post("/api/register", json={
        "agent_id": agent_id, "name": agent_id.title(),
        "capabilities": ["shell"], "endpoint": None,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


def _auth(secret):
    return {"Authorization": f"Bearer {secret}"}


def _evid():
    return uuid.uuid4().hex


def test_kv_store_crud(client):
    d = _register(client, "kv-agent")
    sec = d["secret"]

    # put
    r = client.put("/api/kv/task:T1/wip_context",
                   json={"key": "wip_context", "value": {"done": ["a"], "next": ["b"]}},
                   headers=_auth(sec))
    assert r.status_code == 200, r.text

    # get
    r = client.get("/api/kv/task:T1/wip_context", headers=_auth(sec))
    assert r.status_code == 200
    assert r.json()["value"]["done"] == ["a"]

    # list with prefix
    client.put("/api/kv/task:T1/decision", json={"key": "decision", "value": "go"},
               headers=_auth(sec))
    r = client.get("/api/kv/task:T1", params={"prefix": "wi"}, headers=_auth(sec))
    assert r.status_code == 200
    assert [i["key"] for i in r.json()["items"]] == ["wip_context"]

    # delete
    r = client.delete("/api/kv/task:T1/wip_context", headers=_auth(sec))
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert client.get("/api/kv/task:T1/wip_context", headers=_auth(sec)).status_code == 404


def test_kv_namespace_permission(client):
    d = _register(client, "perm-agent")
    sec = d["secret"]
    # writing someone else's agent namespace → 403
    r = client.put("/api/kv/agent:someone-else/x", json={"key": "x", "value": 1},
                   headers=_auth(sec))
    assert r.status_code == 403
    # writing a task namespace is fine
    r = client.put("/api/kv/task:T2/x", json={"key": "x", "value": 1}, headers=_auth(sec))
    assert r.status_code == 200


def test_sop_seeded_and_delivered(client):
    d = _register(client, "sop-agent")
    # registration carries the SOP
    assert len(d["sop"]) >= 7, "default SOP rules should be seeded"
    keys = {r["rule_key"] for r in d["sop"]}
    assert "sop.handoff" in keys and "sop.pickup" in keys

    # GET /api/sop also works
    r = client.get("/api/sop", headers=_auth(d["secret"]))
    assert r.status_code == 200
    assert len(r.json()["sop"]) >= 7


def test_handoff_flow(client):
    a = _register(client, "agent-a")
    b = _register(client, "agent-b")
    sec_a, sec_b = a["secret"], b["secret"]

    # A creates a task and starts it
    client.post("/api/events", json={
        "event_id": _evid(), "task_id": "HT1", "type": "created",
        "payload": {"title": "Handoff me", "assignee": "agent-a"},
    }, headers=_auth(sec_a))
    client.post("/api/events", json={
        "event_id": _evid(), "task_id": "HT1", "type": "started", "payload": {},
    }, headers=_auth(sec_a))
    # A writes WIP context KV (SOP rule)
    client.put("/api/kv/task:HT1/wip_context",
               json={"key": "wip_context", "value": {"next": "finish tests"}},
               headers=_auth(sec_a))

    # A requests handoff to B
    r = client.post("/api/tasks/HT1/handoff",
                    json={"to_agent": "agent-b", "notes": "See KV wip_context"},
                    headers=_auth(sec_a))
    assert r.status_code == 200, r.text
    h_id = r.json()["handoff_id"]

    # B re-registers → sees the pending handoff as WIP
    r = client.post("/api/register", json={"agent_id": "agent-b", "name": "B"})
    wip = r.json()["wip_handoffs"]
    assert len(wip) == 1 and wip[0]["task_id"] == "HT1"

    # B accepts
    r = client.post(f"/api/handoffs/{h_id}/accept", headers=_auth(sec_b))
    assert r.status_code == 200 and r.json()["status"] == "accepted"

    # Timeline has the handoff event
    r = client.get("/api/tasks/HT1", headers={"Authorization": "Bearer test-commander"})
    assert r.status_code == 200
    types = [e["type"] for e in r.json()["events"]]
    assert "handoff_requested" in types


def test_handoff_wrong_agent_cannot_accept(client):
    a = _register(client, "agent-a2")
    b = _register(client, "agent-b2")
    c = _register(client, "agent-c2")
    r = client.post("/api/tasks/HT2/handoff",
                    json={"to_agent": "agent-b2", "notes": "for B"},
                    headers=_auth(a["secret"]))
    h_id = r.json()["handoff_id"]
    # C tries to accept → 403
    r = client.post(f"/api/handoffs/{h_id}/accept", headers=_auth(c["secret"]))
    assert r.status_code == 403
