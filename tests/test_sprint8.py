"""S8 — Sprint 8 tests: W3 full-text search + W5 task links."""
import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture()
def c(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVOY_DB", str(tmp_path / "convoy_s8.db"))
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


def test_w5_task_links(c):
    d = _reg(c, "link-agent", role="engineer")
    sec = d["secret"]
    # create two tasks
    for tid, title in [("L-1", "Parent task"), ("L-2", "Child task")]:
        r = c.post("/api/events", json={"event_id": f"e-{tid}",
                                        "task_id": tid, "type": "created",
                                        "payload": {"title": title}},
                   headers=_auth(sec))
        assert r.status_code == 202
    # link L-1 -> L-2 as parent
    r = c.post("/api/tasks/L-1/links", json={"to_task": "L-2", "kind": "parent"},
               headers=_auth(sec))
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True

    # duplicate link is idempotent
    r = c.post("/api/tasks/L-1/links", json={"to_task": "L-2", "kind": "parent"},
               headers=_auth(sec))
    assert r.json()["created"] is False

    # commander sees links in detail
    r = c.get("/api/tasks/L-1", headers=_cmd())
    links = r.json()["links"]
    assert links["outgoing"][0]["to_task"] == "L-2"
    assert links["outgoing"][0]["kind"] == "parent"
    # incoming on L-2
    r = c.get("/api/tasks/L-2", headers=_cmd())
    assert r.json()["links"]["incoming"][0]["from_task"] == "L-1"

    # invalid kind rejected
    r = c.post("/api/tasks/L-1/links", json={"to_task": "L-2", "kind": "weird"},
               headers=_auth(sec))
    assert r.status_code == 422


def test_w3_search_finds_kv(c):
    d = _reg(c, "search-agent", role="designer")
    sec = d["secret"]
    r = c.put("/api/kv/task:SRC-1/notes",
              json={"key": "notes", "value": {"body": "The quantum waffle needs more syrup"}},
              headers=_auth(sec))
    assert r.status_code == 200

    r = c.get("/api/search", params={"q": "quantum waffle"}, headers=_cmd())
    assert r.status_code == 200
    results = r.json()["results"]
    assert any("quantum" in (res.get("content") or "") for res in results), results

    # secret namespace NOT indexed
    r = c.put("/api/kv/agent:search-agent/token",
              json={"key": "token", "value": "super-secret-xyz"}, headers=_auth(sec))
    assert r.status_code == 200
    r = c.get("/api/search", params={"q": "super-secret"}, headers=_cmd())
    assert all("super-secret" not in (res.get("content") or "") for res in r.json()["results"])


def test_w3_empty_query(c):
    r = c.get("/api/search", params={"q": ""}, headers=_cmd())
    assert r.json()["results"] == []
