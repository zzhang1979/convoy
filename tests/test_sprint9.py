"""S9 — Sprint 9 tests: Agent Read-Only Access & Security Verification."""
import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture()
def c(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVOY_DB", str(tmp_path / "convoy_s9.db"))
    monkeypatch.setenv("CONVOY_COMMANDER_TOKEN", "test-commander")
    with TestClient(app) as cl:
        yield cl


def _reg(c, agent_id, role=None):
    body = {"agent_id": agent_id, "name": agent_id, "capabilities": ["shell"]}
    if role:
        body["role"] = role
    r = c.post("/api/register", json=body)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _auth(sec):
    return {"Authorization": f"Bearer {sec}"}


def _cmd():
    return {"Authorization": "Bearer test-commander"}


def test_agent_read_only_views(c):
    # 1. Register agent
    d = _reg(c, "reader-agent", role="engineer")
    sec = d["secret"]
    headers = _auth(sec)

    # 2. Board read access for agent
    r = c.get("/api/board", headers=headers)
    assert r.status_code == 200
    assert "board" in r.json()

    # 3. Create a task using agent token
    r = c.post("/api/events", json={
        "event_id": "ev-s9-1",
        "task_id": "T-9",
        "type": "created",
        "payload": {"title": "Sprint 9 Task", "project": "beta"}
    }, headers=headers)
    assert r.status_code == 202

    # 4. Task detail read access for agent
    r = c.get("/api/tasks/T-9", headers=headers)
    assert r.status_code == 200
    assert r.json()["task_id"] == "T-9"
    assert r.json()["projection"]["title"] == "Sprint 9 Task"

    # 5. Task links read access for agent
    r = c.get("/api/tasks/T-9/links", headers=headers)
    assert r.status_code == 200
    assert "outgoing" in r.json()

    # 6. Search read access for agent
    r = c.put("/api/kv/task:T-9/notes", json={
        "key": "notes",
        "value": {"body": "Secret quantum waffles"}
    }, headers=headers)
    assert r.status_code == 200

    r = c.get("/api/search", params={"q": "quantum waffles"}, headers=headers)
    assert r.status_code == 200
    assert len(r.json()["results"]) > 0


def test_agent_write_escalation_denied(c):
    d = _reg(c, "limited-agent", role="designer")
    sec = d["secret"]
    headers = _auth(sec)

    # Agent cannot change role hourly rates
    r = c.put("/api/roles/designer", json={"cost_per_hour": 50.0}, headers=headers)
    assert r.status_code in (401, 403)

    # Agent cannot design schedule ranges
    r = c.put("/api/agents/limited-agent/schedule", json={
        "work_start": "08:00",
        "work_end": "16:00"
    }, headers=headers)
    assert r.status_code in (401, 403)

    # Agent cannot view full financial cost aggregate report
    r = c.get("/api/costs", headers=headers)
    assert r.status_code in (401, 403)

    r = c.get("/api/costs/full", headers=headers)
    assert r.status_code in (401, 403)

    # Agent cannot GET the direct agent registry listing
    r = c.get("/api/agents", headers=headers)
    assert r.status_code in (401, 403)


def test_invalid_tokens_rejected(c):
    headers = _auth("fake-secret-token")

    r = c.get("/api/board", headers=headers)
    assert r.status_code in (401, 403)

    r = c.get("/api/tasks/T-9", headers=headers)
    assert r.status_code in (401, 403)


def test_commander_has_full_access(c):
    d = _reg(c, "worker-agent", role="qa")
    sec = d["secret"]

    # Create task
    c.post("/api/events", json={
        "event_id": "ev-s9-cmd",
        "task_id": "T-10",
        "type": "created",
        "payload": {"title": "Task 10"}
    }, headers=_auth(sec))

    # Commander token gets board, details, costs, and updates schedule
    assert c.get("/api/board", headers=_cmd()).status_code == 200
    assert c.get("/api/tasks/T-10", headers=_cmd()).status_code == 200
    assert c.get("/api/costs/full", headers=_cmd()).status_code == 200

    r = c.put("/api/agents/worker-agent/schedule", json={
        "work_start": "10:00",
        "work_end": "18:00"
    }, headers=_cmd())
    assert r.status_code == 200
