#!/usr/bin/env python3
"""Convoy S1.7 — integration test.

Scenario: three agents (alpha, bravo, charlie) register, work on tasks, report
events, and the derived board reflects reality.

- Starts the Convoy server itself (fresh temp DB, random port) unless
  CONVOY_URL points at an already-running instance.
- Stdlib only (urllib) — no pytest/requests needed.
- Exit code 0 = PASS, 1 = FAIL, 2 = could not start/verify server.

Usage:
    python3 tests/integration_test.py
    CONVOY_URL=http://127.0.0.1:8000 python3 tests/integration_test.py
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDER_TOKEN = os.environ.get("CONVOY_COMMANDER_TOKEN", "s1.7-commander-token")
BASE_URL = os.environ.get("CONVOY_URL", "").rstrip("/")

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def api(method: str, path: str, body: dict | None = None,
        token: str | None = None) -> tuple[int, dict]:
    url = BASE_URL + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except json.JSONDecodeError:
            return e.code, {}
    except urllib.error.URLError as e:
        return -1, {"error": str(e.reason)}


def wait_health(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=2) as resp:
                return resp.status == 200
        except Exception:
            time.sleep(0.5)
    return False


def pick_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server() -> subprocess.Popen | None:
    """Boot the server on a fresh temp DB + random port; returns process."""
    port = pick_port()
    tmp_db = f"/tmp/convoy-s17-{uuid.uuid4().hex[:8]}.db"
    env = dict(os.environ, CONVOY_DB=tmp_db, CONVOY_COMMANDER_TOKEN=COMMANDER_TOKEN)
    # Design-doc layout: server/ package (server.main:app). Fallback: flat main:app.
    candidates = [
        [str(REPO_ROOT / ".venv/bin/uvicorn"), "server.main:app"],
        [str(REPO_ROOT / ".venv/bin/uvicorn"), "main:app"],
    ]
    for cmd, app in candidates:
        try:
            proc = subprocess.Popen(
                [*cmd, app, "--host", "127.0.0.1", "--port", str(port)],
                cwd=REPO_ROOT if "server.main" in app else REPO_ROOT / "server",
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if wait_health(f"http://127.0.0.1:{port}"):
                global BASE_URL
                BASE_URL = f"http://127.0.0.1:{port}"
                return proc
            proc.kill()
        except FileNotFoundError:
            continue
    return None


def main() -> int:
    global BASE_URL
    own_server = False
    if not BASE_URL:
        proc = start_server()
        if proc is None:
            print("FATAL: could not start Convoy server (is .venv set up? run: "
                  "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)")
            return 2
        own_server = True
        print(f"server started on {BASE_URL} (own process, pid {proc.pid})")
    else:
        if not wait_health(BASE_URL):
            print(f"FATAL: no healthy server at {BASE_URL}")
            return 2
        print(f"server already running at {BASE_URL}")

    try:
        return run_scenario()
    finally:
        if own_server and "proc" in dir() and proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def run_scenario() -> int:
    print("\n== 1. health ==")
    code, body = api("GET", "/api/health")
    check("GET /api/health → 200", code == 200, f"got {code}")
    check("health reports ok", body.get("status") == "ok", str(body))

    print("\n== 2. register 3 agents ==")
    agents = {"alpha": "Alpha Worker", "bravo": "Bravo Builder", "charlie": "Charlie Docs"}
    secrets: dict[str, str] = {}
    for aid, name in agents.items():
        code, body = api("POST", "/api/register",
                         {"agent_id": aid, "name": name,
                          "capabilities": ["coding"], "endpoint": f"http://agent-{aid}"})
        check(f"register {aid} → 2xx", 200 <= code < 300, f"got {code}: {body}")
        check(f"register {aid} returns secret", bool(body.get("secret")), str(body))
        secrets[aid] = body.get("secret", "")

    print("\n== 3. events: alpha completes T1 (created→started→progress→done) ==")
    ev = lambda aid, tid, etype, payload=None, eid=None: api(
        "POST", "/api/events",
        {"event_id": eid or uuid.uuid4().hex, "task_id": tid, "type": etype,
         "payload": payload or {}},
        token=secrets[aid])
    for etype, payload in [("created", {"title": "Build the widget"}),
                           ("started", {}),
                           ("progress", {"note": "halfway", "pct": 50}),
                           ("done", {"summary": "widget shipped"})]:
        code, body = ev("alpha", "T1", etype, payload)
        check(f"T1 {etype} → 202", code == 202, f"got {code}: {body}")

    print("\n== 4. events: bravo stuck on T2 ==")
    for etype, payload in [("created", {"title": "Fix the auth bug"}),
                           ("started", {}),
                           ("blocked_on", {"reason": "missing Infisical token"})]:
        code, body = ev("bravo", "T2", etype, payload)
        check(f"T2 {etype} → 202", code == 202, f"got {code}: {body}")

    print("\n== 5. events: charlie publishes artifact on T3 ==")
    for etype, payload in [("created", {"title": "Write the docs"}),
                           ("started", {}),
                           ("artifact_published", {"url": "http://docs/T3", "kind": "doc"})]:
        code, body = ev("charlie", "T3", etype, payload)
        check(f"T3 {etype} → 202", code == 202, f"got {code}: {body}")

    print("\n== 6. idempotency: replay an event_id → duplicate, not double-append ==")
    eid = uuid.uuid4().hex
    code1, body1 = ev("alpha", "T1", "heartbeat", {}, eid)
    code2, body2 = ev("alpha", "T1", "heartbeat", {}, eid)
    check("first append → 202", code1 == 202, f"got {code1}")
    check("replay handled gracefully (202/409)", code2 in (202, 409), f"got {code2}: {body2}")
    dup_ok = (body2.get("status") == "duplicate") or code2 == 409
    check("replay reported as duplicate", dup_ok, str(body2))

    print("\n== 7. heartbeats keep agents fresh ==")
    for aid in agents:
        code, body = ev(aid, None, "heartbeat", {}, uuid.uuid4().hex)
        check(f"heartbeat {aid} → 202", code == 202, f"got {code}: {body}")

    print("\n== 8. auth: no/unknown token rejected ==")
    code, body = api("POST", "/api/events",
                     {"event_id": uuid.uuid4().hex, "type": "heartbeat", "payload": {}})
    check("events without token → 401", code == 401, f"got {code}")
    code, body = api("POST", "/api/events",
                     {"event_id": uuid.uuid4().hex, "type": "heartbeat", "payload": {}},
                     token="bogus-secret")
    check("events with bad token → 401", code == 401, f"got {code}")

    print("\n== 9. board requires commander token, then reflects reality ==")
    code, body = api("GET", "/api/board")
    check("board without token → 401/403", code in (401, 403), f"got {code}")
    code, body = api("GET", "/api/board", token=COMMANDER_TOKEN)
    check("board with commander token → 200", code == 200, f"got {code}: {str(body)[:200]}")

    # Derive statuses from the board payload however it is shaped; the design
    # contract says bands: running / stuck / done-today (or a per-task status map).
    blob = json.dumps(body)
    board = body.get("board", body)
    check("board mentions T1 (done today)", "T1" in blob, "")
    check("board mentions T2 (stuck)", "T2" in blob, "")
    check("board mentions T3 (review/running)", "T3" in blob, "")
    # stuck flag surfaced somewhere
    check("board surfaces stuck signal", ("stuck" in blob.lower()
                                          or "blocked" in blob.lower()
                                          or "missing Infisical" in blob), "")

    print("\n== 10. agents registry ==")
    code, body = api("GET", "/api/agents", token=COMMANDER_TOKEN)
    check("agents → 200", code == 200, f"got {code}")
    aids = {a.get("agent_id") for a in body.get("agents", [])}
    check("all 3 agents registered", aids == set(agents), f"got {aids}")
    fresh = [a for a in body.get("agents", []) if a.get("last_heartbeat")]
    check("agents have heartbeats recorded", len(fresh) >= 3, f"{len(fresh)}/3")

    print("\n" + "=" * 56)
    if FAILURES:
        print(f"RESULT: FAIL — {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("RESULT: PASS — all checks green ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
