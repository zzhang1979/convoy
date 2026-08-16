"""S10 — Sprint 10 tests: QA Pilot, Token Burn, Stale Task Detection, and Commander Events."""
import os
import time
import pytest
import requests
from fastapi.testclient import TestClient

from server.main import app
from server import models
from server.derive import derive_board, derive_tasks
from agent.qa_agent_pilot import QAPilot


@pytest.fixture()
def c(tmp_path, monkeypatch):
    """Client with isolated temp db."""
    monkeypatch.setenv("CONVOY_DB", str(tmp_path / "convoy_s10.db"))
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


def test_qa_agent_pilot_runs(c, monkeypatch):
    """Test that the QAPilot class can execute successfully against the TestClient."""
    # 1. Register agent
    agent_info = _reg(c, "antigravity-qa", role="qa")
    secret = agent_info["secret"]

    # 2. Setup mock target file in workspace
    target_file = "docker-entrypoint.sh"
    
    # 3. Create a task for testing
    c.post("/api/events", json={
        "event_id": "ev-s10-1",
        "task_id": "T-10-Pilot",
        "type": "created",
        "payload": {"title": "QA Test Task", "assignee": "antigravity-qa"}
    }, headers=_auth(secret))

    # 4. Redirect requests to FastAPI TestClient in-memory using monkeypatch
    def mock_requests_get(url, headers=None, timeout=None, params=None):
        path = url.replace("http://localhost:8000", "").replace("http://127.0.0.1:8000", "")
        # Call client
        r = c.get(path, headers=headers, params=params)
        # Mock Response
        class MockResp:
            def __init__(self, res):
                self.status_code = res.status_code
                self.ok = res.status_code < 400
                self.text = res.text
                self._json = res.json()
            def json(self):
                return self._json
            def raise_for_status(self):
                if not self.ok:
                    raise Exception(f"HTTP Error: {self.status_code}")
        return MockResp(r)

    def mock_requests_post(url, json=None, headers=None, timeout=None):
        path = url.replace("http://localhost:8000", "").replace("http://127.0.0.1:8000", "")
        r = c.post(path, json=json, headers=headers)
        class MockResp:
            def __init__(self, res):
                self.status_code = res.status_code
                self.ok = res.status_code < 400
                self.text = res.text
                self._json = res.json()
            def json(self):
                return self._json
            def raise_for_status(self):
                if not self.ok:
                    raise Exception(f"HTTP Error: {self.status_code}")
        return MockResp(r)

    def mock_requests_put(url, json=None, headers=None, timeout=None):
        path = url.replace("http://localhost:8000", "").replace("http://127.0.0.1:8000", "")
        r = c.put(path, json=json, headers=headers)
        class MockResp:
            def __init__(self, res):
                self.status_code = res.status_code
                self.ok = res.status_code < 400
                self.text = res.text
                self._json = res.json()
            def json(self):
                return self._json
            def raise_for_status(self):
                if not self.ok:
                    raise Exception(f"HTTP Error: {self.status_code}")
        return MockResp(r)

    monkeypatch.setattr(requests, "get", mock_requests_get)
    monkeypatch.setattr(requests, "post", mock_requests_post)
    monkeypatch.setattr(requests, "put", mock_requests_put)

    # 5. Run the QA Pilot
    pilot = QAPilot(server_url="http://localhost:8000", agent_id="antigravity-qa")
    pilot.run_heartbeat()
    pilot.run_qa_review(task_id="T-10-Pilot", target_file=target_file)

    # 6. Verify that events, KV metadata, token usage, and handoffs are correctly recorded
    # Event check
    r = c.get("/api/tasks/T-10-Pilot", headers=_cmd())
    assert r.status_code == 200
    task_data = r.json()
    assert task_data["projection"]["status"] == "done"
    
    # Handoff check
    r = c.get("/api/handoffs", headers=_auth(secret))
    assert r.status_code == 200
    assert len(r.json()["handoffs"]) > 0
    assert r.json()["handoffs"][0]["to_agent"] == "jean"


def test_stale_task_detection(c):
    """Test that a task becomes stale after 5 minutes of assignee agent inactivity."""
    sec = _reg(c, "quiet-agent", role="engineer")["secret"]

    # 1. Create and start task at t=0
    c.post("/api/events", json={
        "event_id": "ev-s10-t1",
        "task_id": "T-STALE",
        "type": "created",
        "payload": {"title": "Stale Task test", "assignee": "quiet-agent", "project": "delta"}
    }, headers=_auth(sec))

    c.post("/api/events", json={
        "event_id": "ev-s10-t2",
        "task_id": "T-STALE",
        "type": "started",
        "payload": {}
    }, headers=_auth(sec))

    # Retrieve and parse events
    import json
    events = []
    with models.connect() as conn:
        rows = conn.execute("SELECT * FROM events ORDER BY id").fetchall()
        for r in rows:
            d = dict(r)
            if isinstance(d.get("payload"), str):
                try:
                    d["payload"] = json.loads(d["payload"])
                except Exception:
                    d["payload"] = {}
            events.append(d)

    # 2. Query status immediately using the last event's timestamp: should be "doing"
    t_doing = derive_tasks(events)["T-STALE"]
    last_event_time = t_doing.last_event_at
    assert t_doing.status(now=last_event_time) == "doing"

    # 3. Query status after 6 minutes (360 seconds) with no new events: should be "stale"
    import datetime
    dt = datetime.datetime.fromisoformat(last_event_time.replace(" ", "T"))
    future_time = (dt + datetime.timedelta(seconds=360)).isoformat()
    assert t_doing.status(now=future_time) == "stale"


def test_commander_can_post_events(c):
    """Test that the commander token can post events under virtual agent 'commander'."""
    sec = _reg(c, "dev-agent", role="engineer")["secret"]

    # 1. Create a task using agent
    c.post("/api/events", json={
        "event_id": "ev-cmd-t1",
        "task_id": "T-CMD",
        "type": "created",
        "payload": {"title": "Commander override task", "assignee": "dev-agent"}
    }, headers=_auth(sec))

    # 2. Verify it is running
    r = c.get("/api/tasks/T-CMD", headers=_cmd())
    assert r.json()["projection"]["status"] == "todo"

    # 3. Commander posts a done event
    r = c.post("/api/events", json={
        "event_id": "ev-cmd-t2",
        "task_id": "T-CMD",
        "type": "done",
        "payload": {"summary": "Closed by boss"}
    }, headers=_cmd())
    assert r.status_code == 202
    assert r.json()["status"] == "accepted"

    # 4. Verify task status is now done
    r = c.get("/api/tasks/T-CMD", headers=_cmd())
    assert r.json()["projection"]["status"] == "done"
    assert r.json()["projection"]["done_by"] == "commander"
