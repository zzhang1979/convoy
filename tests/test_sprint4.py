"""S4.5 — Sprint 4 integration tests: token usage intake + aggregation + cost merge."""
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


def test_usage_report_and_summary(client):
    d = _reg(client, "usage-agent", role="engineer")
    sec = d["secret"]

    # report 2 calls
    r = client.post("/api/usage", json={
        "model": "gpt-4o", "tokens_in": 100000, "tokens_out": 20000, "task_id": "T1",
    }, headers=_auth(sec))
    assert r.status_code == 200 and r.json()["status"] == "recorded"

    client.post("/api/usage", json={
        "model": "gpt-4o", "tokens_in": 50000, "tokens_out": 10000, "task_id": "T2",
    }, headers=_auth(sec))

    r = client.get("/api/usage", headers=_cmd())
    assert r.status_code == 200
    body = r.json()
    agent = next(a for a in body["per_agent"] if a["agent_id"] == "usage-agent")
    assert agent["tokens_in"] == 150000
    assert agent["tokens_out"] == 30000
    assert agent["calls"] == 2
    assert len(agent["by_model"]) == 1  # same model grouped


def test_usage_filter_by_agent_and_task(client):
    d1 = _reg(client, "ua-1", role="engineer")
    d2 = _reg(client, "ua-2", role="designer")
    client.post("/api/usage", json={"model": "m", "tokens_in": 10, "tokens_out": 5},
                headers=_auth(d1["secret"]))
    client.post("/api/usage", json={"model": "m", "tokens_in": 20, "tokens_out": 5},
                headers=_auth(d2["secret"]))
    client.post("/api/usage", json={"model": "m", "tokens_in": 100, "tokens_out": 50,
                                    "task_id": "special"},
                headers=_auth(d1["secret"]))

    r = client.get("/api/usage", params={"agent_id": "ua-1"}, headers=_cmd())
    a = r.json()["per_agent"][0]
    assert a["tokens_in"] == 110

    r = client.get("/api/usage", params={"task_id": "special"}, headers=_cmd())
    a = r.json()["per_agent"][0]
    assert a["agent_id"] == "ua-1" and a["tokens_in"] == 100


def test_token_cost_math(client):
    # engineer role: default in=3/1M, out=15/1M
    d = _reg(client, "cost-agent", role="engineer")
    client.post("/api/usage", json={"model": "gpt-4o", "tokens_in": 1000000, "tokens_out": 1000000},
                headers=_auth(d["secret"]))
    r = client.get("/api/usage", headers=_cmd())
    agent = r.json()["per_agent"][0]
    # 1M in × $3 + 1M out × $15 = $18
    assert abs(agent["token_cost"] - 18.0) < 0.01


def test_role_token_cost_config(client):
    r = client.put("/api/roles/engineer/token-costs",
                   json={"in_cost_per_1m": 1.0, "out_cost_per_1m": 5.0}, headers=_cmd())
    assert r.status_code == 200
    roles = client.get("/api/roles", headers=_cmd()).json()["roles"]
    eng = next(x for x in roles if x["role_name"] == "engineer")
    assert eng["in_cost_per_1m"] == 1.0 and eng["out_cost_per_1m"] == 5.0


def test_full_cost_merge(client):
    d = _reg(client, "full-agent", role="engineer")
    # token usage: 1M in + 1M out at default rates = $18
    client.post("/api/usage", json={"model": "gpt-4o", "tokens_in": 1000000, "tokens_out": 1000000},
                headers=_auth(d["secret"]))
    r = client.get("/api/costs/full", headers=_cmd())
    assert r.status_code == 200
    agent = next(a for a in r.json()["per_agent"] if a["agent_id"] == "full-agent")
    assert agent["token_cost"] == 18.0
    assert agent["total_cost"] == agent["cost"] + 18.0
    assert r.json()["total"]["grand_total"] >= 18.0
