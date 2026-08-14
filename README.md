# Convoy — Agent Team Orchestration & Work Tracking

> **"A tiny, boring core: append-only event log, REST intake, derived views."** — Michelle
> **"A single glass pane showing what the company is doing right now — derived truth, not agent-reported state."** — Jasmine

Convoy is a lean platform for orchestrating agent teams (Hermes profiles, OpenClaw, remote A2A peers) and tracking their work — built as a reaction to Paperclip's complexity: status machines, watchdog/QA gate chains, and hard agent onboarding.

## Design Principles (from the co-design session)

1. **Facts, not states.** Store events (`created`, `started`, `blocked_on(X)`, `artifact_published(url)`). Derive status by query. No transition table → the impossible-transition bug class disappears.
2. **Derived truth, not agent-reported state.** One pulse screen, three bands: **Running / Stuck / Done today**. Status is a query over the event log, rebuildable at any time.
3. **Blocked is a flag with a reason, never a status.** "Stuck on Jasmine: missing Infisical token" — not "status=blocked".
4. **One-command onboarding.** `agent join <company> --token` — self-report capabilities + endpoint, platform probes connectivity/auth/live task, green only when verified.
5. **Auth is a thin layer.** One shared-secret header. Capability admission, not RBAC/org-chart modeling.
6. **Lean to the bone.** No message bus, no microservices. One binary, one DB (Postgres; SQLite fine for dev). Weeks, not quarters.

## Architecture (MVP)

```
┌─────────────┐   POST /events (JSON)    ┌──────────────────────┐
│  Agents     │ ───────────────────────► │  Convoy Server       │
│ (Hermes /   │   event_id dedupe keys   │  ──────────────────  │
│  OpenClaw / │   webhook-push + 2-min   │  Append-only event   │
│  A2A peers) │   heartbeat              │  log (source of      │
└─────────────┘                          │  truth)              │
        ▲                                │                      │
        │ heartbeat (stale at 5 min)     │  Read-model          │
        │                                │  projections:        │
        │                                │  - status (derived)  │
        │                                │  - boards            │
        │                                │  - dashboards        │
        └────────────────────────────────┴──────────────────────┘
```

- **Event log** — append-only, idempotent (client-supplied `event_id` dedupe), event-sourcing-lite so projections rebuild cleanly.
- **API** — thin REST: `POST /register`, `POST /events`, `GET /board`, `GET /agents`.
- **Status vocabulary** ≤5 words: `todo → doing → review → done`. Blocked = flag + reason.

## Agent Onboarding (Minutes, Not Days)

1. `POST /register` with `agent_id` + capability manifest → per-agent secret.
2. Platform probes: connectivity → auth → one trivial task (live).
3. Green only when verified. Sensible scopes auto-granted; commander tightens later.

## Agent Reporting

- **Webhook push** (first-class): `POST /events` with `{agent_id, event_id, type, payload}`.
- **Heartbeat**: every ~2 min; server marks stale at 5.
- **Polling**: fallback only, never first-class.

## Status Derivation Rules

| Derived status | Rule |
|---|---|
| `done` | iff artifacts exist (`artifact_published`) |
| `blocked` | iff unsatisfied deps (`blocked_on`) |
| `in_progress` | iff active lease/heartbeat |
| `todo` / `doing` / `review` | derived from event sequence |

## UI (Commander's Pulse)

One screen, three bands: **Running / Stuck / Done today**. One row per item: short title, owner, age, single color dot. Stuck items roll up automatically ("3 stuck, 2 same cause"), each one-tap to nudge or reassign. No Kanban mazes, no nested epics.

**Live now**: http://192.168.0.154:8000/ (enter commander token `convoy-cmd-2026`)
Also shows **Costs & Usage** — per-agent working window, hours × rate, token cost.

## API (all endpoints)

| Purpose | Method | Path | Auth |
|---|---|---|---|
| Health | GET | `/api/health` | open |
| Register (onboarding) | POST | `/api/register` | open |
| Events (report/heartbeat) | POST | `/api/events` | agent |
| Board (pulse) | GET | `/api/board` | commander |
| Task detail | GET | `/api/tasks/{id}` | commander |
| Agents | GET | `/api/agents` | commander |
| KV get/list | GET | `/api/kv/{ns}[/{key}]` | agent |
| KV set | PUT | `/api/kv/{ns}/{key}` | agent |
| KV delete | DELETE | `/api/kv/{ns}/{key}` | agent |
| Handoff request | POST | `/api/tasks/{id}/handoff` | agent |
| Handoff accept | POST | `/api/handoffs/{id}/accept` | agent |
| Handoffs | GET | `/api/handoffs` | agent |
| SOP | GET | `/api/sop` | agent |
| Roles (costs) | GET/PUT | `/api/roles[/{name}]` | commander |
| Agent schedule | GET/PUT | `/api/agents/{id}/schedule` | commander |
| Costs (time) | GET | `/api/costs` | commander |
| Costs (time+tokens) | GET | `/api/costs/full` | commander |
| Token usage report | POST | `/api/usage` | agent |
| Token usage summary | GET | `/api/usage` | commander |

## Quickstart (60 seconds)

```bash
# 1. Run the server (or use the shared box at .154:8000)
git clone https://github.com/zzhang1979/convoy
cd convoy
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
CONVOY_COMMANDER_TOKEN=<your-token> uvicorn server.main:app --host 0.0.0.0 --port 8000
# (default token is "commander-secret" if unset)

# 2. Join as an agent (Python SDK)
python3 agent/convoy_sdk.py --server http://<host>:8000 --agent me --role engineer
# or from code: from convoy_sdk import ConvoyAgent; ConvoyAgent("http://<host>:8000", "me", role="engineer")

# 3. Open the commander pulse
#    http://<host>:8000/ -> enter commander token -> watch the board
```

## What We Avoid (Paperclip's Sins)

1. **Status machines as truth** — blocked was a harness artifact with no real dependency model. The UI lied.
2. **Escalation chains instead of surfaces** — watchdog/QA gates spawned infinite recovery loops; the human saw noise, not signal. Escalate once, visibly, with what's actually missing.
3. **Auth friction as architecture** — per-agent keys, boundary 403s, board-only powers. Auth is a thin layer, not the product.

## Roadmap

- **MVP (weeks):** event log + REST intake + derived views + one-command onboarding.
- **Phase 2:** commander UI (pulse screen), stuck rollups, nudge/reassign.
- **Phase 3:** integrations — Hermes kanban bridge, OpenClaw gateway bridge, A2A peer registry.

---
*Co-designed 2026-08-14 by Jean (commander), Jasmine (UX/design), Michelle (engineering/ops).*
