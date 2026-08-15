"""S7.5 — Sprint 7 integration tests: W1 drill-down, W2 project, W4 role, W6 story."""
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


def _ev(secret, eid, task, typ, payload):
    r = client.post("/api/events", json={"event_id": eid, "task_id": task,
                                         "type": typ, "payload": payload},
                    headers=_auth(secret))
    assert r.status_code == 202, r.text


def test_w2_project_grouping(client):
    d = _reg(client, "proj-agent", role="engineer")
    sec = d["secret"]
    _ev(sec, "p1", "PT-1", "created", {"title": "Convoy feature", "project": "convoy"})
    _ev(sec, "p2", "PT-1", "started", {})
    _ev(sec, "p3", "GP-1", "created", {"title": "GPSnet thing", "project": "gpsnet"})
    _ev(sec, "p4", "GP-1", "started", {})

    r = client.get("/api/board", params={"project": "convoy"}, headers=_cmd())
    ids = [t["task_id"] for t in r.json()["board"]["running"]]
    assert "PT-1" in ids and "GP-1" not in ids

    r = client.get("/api/board", headers=_cmd())
    assert "convoy" in r.json()["projects"] and "gpsnet" in r.json()["projects"]


def test_w4_role_snapshot_on_events(client):
    d = _reg(client, "role-agent", role="engineer")
    sec = d["secret"]
    _ev(sec, "r1", "RT-1", "created", {"title": "Role test"})
    _ev(sec, "r2", "RT-1", "progress", {"note": "work"})

    r = client.get("/api/tasks/RT-1", headers=_cmd())
    evs = r.json()["events"]
    for e in evs:
        assert e["payload"].get("role") == "engineer", f"role missing on {e['type']}"
    # projection roles map has agent -> role
    assert r.json()["projection"]["roles"].get("role-agent") == "engineer"


def test_w1_drill_down_kv_and_story(client):
    d = _reg(client, "dd-agent", role="designer")
    sec = d["secret"]
    _ev(sec, "d1", "DD-1", "created", {"title": "Drill me", "project": "convoy"})
    # write KV context + user story
    for key, val in [("wip_context", {"done": ["a"], "next": ["b"]}),
                     ("user_story", {"as_a": "commander", "i_want": "drill down",
                                     "so_that": "I track work", "acceptance": ["see events"]})]:
        r = client.put(f"/api/kv/task:DD-1/{key}", json={"value": val}, headers=_auth(sec))
        assert r.status_code == 200, r.text

    r = client.get("/api/tasks/DD-1", headers=_cmd())
    body = r.json()
    assert body["kv"]["wip_context"]["next"] == ["b"]
    assert body["user_story"]["i_want"] == "drill down"
    assert body["projection"]["project"] == "convoy"
    assert body["projection"]["roles"].get("dd-agent") == "designer"


def test_w6_sop_has_story_rule(client):
    d = _reg(client, "sop-agent")
    assert any(r["rule_key"] == "sop.story" for r in d["sop"])


def test_w2_project_in_projection(client):
    d = _reg(client, "pr-agent", role="engineer")
    _ev(d["secret"], "x1", "PR-1", "created", {"title": "X", "project": "alpha"})
    r = client.get("/api/tasks/PR-1", headers=_cmd())
    assert r.json()["projection"]["project"] == "alpha"
