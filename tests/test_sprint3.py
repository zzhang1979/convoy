"""S3.5 — Sprint 3 integration tests: roles/costing, schedules, cost math."""
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


def _reg(client, agent_id, role=None):
    body = {"agent_id": agent_id, "name": agent_id.title(), "capabilities": ["shell"]}
    if role:
        body["role"] = role
    r = client.post("/api/register", json=body)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _auth(secret):
    return {"Authorization": f"Bearer {secret}"}


def _cmd():
    return {"Authorization": "Bearer test-commander"}


def _evid():
    return uuid.uuid4().hex


def test_default_roles_seeded(client):
    r = client.get("/api/roles", headers=_cmd())
    assert r.status_code == 200
    roles = {x["role_name"]: x["cost_per_hour"] for x in r.json()["roles"]}
    assert roles.get("engineer") == 25.0
    assert roles.get("designer") == 30.0
    assert roles.get("commander") == 0.0


def test_set_role_cost(client):
    r = client.put("/api/roles/engineer", json={"cost_per_hour": 40.0}, headers=_cmd())
    assert r.status_code == 200
    assert r.json()["cost_per_hour"] == 40.0
    r = client.get("/api/roles", headers=_cmd())
    roles = {x["role_name"]: x["cost_per_hour"] for x in r.json()["roles"]}
    assert roles["engineer"] == 40.0
    # negative rejected
    r = client.put("/api/roles/engineer", json={"cost_per_hour": -5}, headers=_cmd())
    assert r.status_code == 422


def test_schedule_set_and_get(client):
    # agent must exist first (FK constraint on schedules.agent_id)
    _reg(client, "test-agent")
    r = client.put("/api/agents/test-agent/schedule",
                   json={"role_name": "engineer", "work_start": "22:00", "work_end": "06:00",
                         "timezone": "America/New_York", "max_hours_per_day": 6},
                   headers=_cmd())
    assert r.status_code == 200
    s = r.json()
    assert s["work_start"] == "22:00" and s["work_end"] == "06:00"
    assert s["timezone"] == "America/New_York"
    assert s["max_hours_per_day"] == 6

    # partial update keeps rest
    r = client.put("/api/agents/test-agent/schedule",
                   json={"work_start": "23:00"}, headers=_cmd())
    s = r.json()
    assert s["work_start"] == "23:00"
    assert s["timezone"] == "America/New_York"  # preserved

    r = client.get("/api/agents/test-agent/schedule", headers=_cmd())
    assert r.json()["work_end"] == "06:00"


def test_register_creates_schedule_with_role(client):
    d = _reg(client, "eng-agent", role="engineer")
    assert d["agent_id"] == "eng-agent"
    r = client.get("/api/agents/eng-agent/schedule", headers=_cmd())
    s = r.json()
    assert s["role_name"] == "engineer"
    assert s["work_start"] == "09:00"  # default


def test_cost_math(client):
    # register an engineer, post events with known gaps
    d = _reg(client, "cost-eng", role="engineer")
    sec = d["secret"]

    # create task, start it
    client.post("/api/events", json={
        "event_id": _evid(), "task_id": "CT1", "type": "created",
        "payload": {"title": "Cost me"}, "role": "engineer",
    }, headers=_auth(sec))

    # Manually insert events with controlled timestamps (30 min apart)
    import sqlite3
    from server.models import db_path
    conn = sqlite3.connect(str(db_path()))
    times = ["2026-08-14 09:00:00", "2026-08-14 09:30:00", "2026-08-14 10:00:00"]
    for i, t in enumerate(times):
        conn.execute(
            "INSERT INTO events (event_id, agent_id, task_id, type, payload, received_at) VALUES (?,?,?,?,?,?)",
            (f"ce-{i}", "cost-eng", "CT1", "progress", "{}", t),
        )
    conn.commit()
    conn.close()

    r = client.get("/api/costs", headers=_cmd())
    assert r.status_code == 200
    body = r.json()
    # gaps: 09:00→09:30 = 0.5h, 09:30→10:00 = 0.5h → 1.0h total
    eng = next(a for a in body["per_agent"] if a["agent_id"] == "cost-eng")
    assert eng["role"] == "engineer"
    assert abs(eng["hours"] - 1.0) < 0.01
    assert abs(eng["cost"] - 25.0) < 0.01  # 1h × $25
    assert body["total"]["cost"] >= 25.0


def test_cost_override_per_agent(client):
    d = _reg(client, "prem-eng", role="engineer")
    # override rate to 50
    client.put("/api/agents/prem-eng/schedule",
               json={"cost_override": 50.0}, headers=_cmd())
    import sqlite3
    from server.models import db_path
    conn = sqlite3.connect(str(db_path()))
    conn.execute(
        "INSERT INTO events (event_id, agent_id, task_id, type, payload, received_at) VALUES (?,?,?,?,?,?)",
        ("pe-1", "prem-eng", "CT2", "started", "{}", "2026-08-14 10:00:00"),
    )
    conn.execute(
        "INSERT INTO events (event_id, agent_id, task_id, type, payload, received_at) VALUES (?,?,?,?,?,?)",
        ("pe-2", "prem-eng", "CT2", "progress", "{}", "2026-08-14 10:30:00"),
    )
    conn.commit()
    conn.close()

    r = client.get("/api/costs", headers=_cmd())
    eng = next(a for a in r.json()["per_agent"] if a["agent_id"] == "prem-eng")
    assert abs(eng["rate"] - 50.0) < 0.01
    assert abs(eng["cost"] - 25.0) < 0.01  # 0.5h × $50
