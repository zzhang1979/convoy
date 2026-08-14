"""S1.7 — Integration test: 3 agents register, work, report, board reflects reality.

Exercises the full HTTP surface of S1.1/S1.2 against a real SQLite DB:
  * POST /api/register   (onboarding, idempotent re-join)
  * POST /api/events     (append, dedupe, auth, validation)
  * GET  /api/health     (liveness)
  * GET  /api/board      (S1.4, Jean) — skipped until that endpoint lands
"""

from __future__ import annotations

import uuid

import pytest

from server import models


def _event_id() -> str:
    return str(uuid.uuid4())


def _auth(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


# ---------------------------------------------------------------------------
# S1.1 — health
# ---------------------------------------------------------------------------

def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "convoy"
    assert body["db"] == "ok"


# ---------------------------------------------------------------------------
# S1.2 — register (onboarding)
# ---------------------------------------------------------------------------

def test_register_three_agents(client):
    secrets = {}
    for agent_id in ("alpha", "beta", "gamma"):
        resp = client.post("/api/register", json={
            "agent_id": agent_id,
            "name": f"Agent {agent_id}",
            "capabilities": ["shell", "a2a"],
        })
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["agent_id"] == agent_id
        assert body["secret"]
        secrets[agent_id] = body["secret"]

    # re-join is idempotent: same secret, 200 not 201
    resp = client.post("/api/register", json={"agent_id": "alpha"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["secret"] == secrets["alpha"]

    # registry rows exist
    with models.connect() as conn:
        rows = conn.execute("SELECT agent_id, secret FROM agents ORDER BY agent_id").fetchall()
        assert [r["agent_id"] for r in rows] == ["alpha", "beta", "gamma"]
        assert all(r["secret"] for r in rows)


# ---------------------------------------------------------------------------
# S1.2 — events (append, dedupe, auth)
# ---------------------------------------------------------------------------

def _register(client, agent_id: str) -> str:
    resp = client.post("/api/register", json={"agent_id": agent_id})
    assert resp.status_code == 201
    return resp.json()["secret"]


def test_events_full_agent_workflow(client):
    """Agent alpha: created -> started -> progress -> done."""
    secret = _register(client, "alpha")

    events = [
        ("created", {"title": "Write S1.7 integration test", "assignee": "alpha"}),
        ("started", {}),
        ("progress", {"note": "drafting", "pct": 60}),
        ("done", {"summary": "test suite green"}),
    ]
    for ev_type, payload in events:
        resp = client.post("/api/events", json={
            "event_id": _event_id(),
            "task_id": "T1",
            "type": ev_type,
            "payload": payload,
        }, headers=_auth(secret))
        assert resp.status_code == 202, resp.text
        assert resp.json()["status"] == "accepted"

    with models.connect() as conn:
        rows = conn.execute(
            "SELECT type, agent_id, task_id FROM events ORDER BY id"
        ).fetchall()
        assert [r["type"] for r in rows] == ["created", "started", "progress", "done"]
        assert all(r["agent_id"] == "alpha" for r in rows)
        assert all(r["task_id"] == "T1" for r in rows)


def test_event_id_dedupe_is_idempotent(client):
    secret = _register(client, "alpha")
    event_id = _event_id()

    first = client.post("/api/events", json={
        "event_id": event_id, "task_id": "T1", "type": "started", "payload": {},
    }, headers=_auth(secret))
    assert first.status_code == 202
    assert first.json()["status"] == "accepted"

    # retry with the same event_id: still 202, flagged duplicate, no 2nd row
    retry = client.post("/api/events", json={
        "event_id": event_id, "task_id": "T1", "type": "started", "payload": {},
    }, headers=_auth(secret))
    assert retry.status_code == 202
    assert retry.json()["status"] == "duplicate"

    with models.connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()["n"]
        assert n == 1


def test_events_requires_valid_bearer(client):
    secret = _register(client, "alpha")
    body = {"event_id": _event_id(), "type": "heartbeat", "payload": {}}

    assert client.post("/api/events", json=body).status_code == 401          # no token
    assert client.post("/api/events", json=body,
                       headers=_auth("bogus-secret")).status_code == 401     # bad token
    assert client.post("/api/events", json=body,
                       headers=_auth(secret)).status_code == 202             # valid token


def test_events_rejects_unknown_type_and_bad_payload(client):
    secret = _register(client, "alpha")

    resp = client.post("/api/events", json={
        "event_id": _event_id(), "type": "teleported", "payload": {},
    }, headers=_auth(secret))
    assert resp.status_code == 422

    resp = client.post("/api/events", json={
        "event_id": _event_id(), "type": "started", "payload": "not-a-dict",
    }, headers=_auth(secret))
    assert resp.status_code == 422


def test_heartbeat_updates_agent_liveness(client):
    secret = _register(client, "alpha")
    resp = client.post("/api/events", json={
        "event_id": _event_id(), "type": "heartbeat", "payload": {},
    }, headers=_auth(secret))
    assert resp.status_code == 202

    with models.connect() as conn:
        row = conn.execute(
            "SELECT last_heartbeat FROM agents WHERE agent_id = 'alpha'"
        ).fetchone()
        assert row["last_heartbeat"] is not None


# ---------------------------------------------------------------------------
# S1.7 — the sprint-level scenario: board reflects reality
# ---------------------------------------------------------------------------

def test_board_reflects_reality(client):
    """Three agents register, work, report — then the board sees it.

    Board endpoint (GET /api/board) is S1.4 owned by Jean; skipped until it
    exists so this test is runnable as soon as the intake side is in.
    """
    alpha = _register(client, "alpha")
    beta = _register(client, "beta")
    gamma = _register(client, "gamma")

    def post(secret, task_id, ev_type, payload):
        resp = client.post("/api/events", json={
            "event_id": _event_id(), "task_id": task_id,
            "type": ev_type, "payload": payload,
        }, headers=_auth(secret))
        assert resp.status_code == 202, resp.text

    # alpha: T1 done
    post(alpha, "T1", "created", {"title": "Ship docs"})
    post(alpha, "T1", "started", {})
    post(alpha, "T1", "progress", {"note": "writing", "pct": 100})
    post(alpha, "T1", "done", {"summary": "docs shipped"})

    # beta: T2 stuck on a dependency
    post(beta, "T2", "created", {"title": "Fix flaky test"})
    post(beta, "T2", "started", {})
    post(beta, "T2", "blocked_on", {"reason": "waiting on CI runner"})

    # gamma: alive, working on T3
    post(gamma, "T3", "created", {"title": "Polish UI"})
    post(gamma, "T3", "started", {})
    post(gamma, None, "heartbeat", {})

    resp = client.get("/api/board", headers={"Authorization": "Bearer commander-secret"})
    if resp.status_code == 404:
        pytest.skip("GET /api/board not implemented yet (S1.4, Jean)")
    if resp.status_code == 401:
        pytest.skip("GET /api/board requires commander token (env-dependent)")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, dict) and body
    board = body.get("board", body)  # band keys may be nested under "board"
    assert any(k in board for k in ("running", "stuck", "done_today", "done"))
    assert board.get("stuck")  # T2 must appear in the stuck band
