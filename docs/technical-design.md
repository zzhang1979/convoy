# Convoy — Technical Design (MVP)

## Stack

- **Server:** Python FastAPI (single process, no workers needed for MVP) — matches existing Levi&Co stack familiarity.
- **DB:** SQLite for dev / Postgres for prod (single table: `events`).
- **Storage:** Append-only event log. Read models built in-memory or via simple SQL projections.

## Data Model

### `events` (append-only, source of truth)

```sql
CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT NOT NULL UNIQUE,     -- client-supplied dedupe key
    agent_id    TEXT NOT NULL,
    task_id     TEXT,                     -- optional, groups events
    type        TEXT NOT NULL,            -- created|started|blocked_on|unblocked|artifact_published|progress|heartbeat|done|cancelled
    payload     TEXT NOT NULL DEFAULT '{}',  -- JSON: reason, url, note, deps
    received_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### `agents` (registration)

```sql
CREATE TABLE agents (
    agent_id        TEXT PRIMARY KEY,
    name            TEXT,
    secret          TEXT NOT NULL,        -- per-agent bearer token
    capabilities    TEXT NOT NULL DEFAULT '[]',  -- JSON array
    endpoint        TEXT,                 -- webhook target (optional)
    joined_at       TEXT NOT NULL DEFAULT (datetime('now')),
    last_heartbeat  TEXT
);
```

## REST API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/register` | open (one-time) | agent joins: `{agent_id, name, capabilities, endpoint}` → `{agent_id, secret}` |
| POST | `/api/events` | `Authorization: Bearer <agent secret>` | append event: `{event_id, task_id, type, payload}` → `202` |
| GET | `/api/board` | commander token | derived board: running/stuck/done-today |
| GET | `/api/agents` | commander token | agent registry + heartbeat status |
| GET | `/api/tasks/{task_id}` | commander token | task timeline (events) |
| GET | `/api/health` | open | liveness |

## Event Types

| Type | Payload | Effect on derived status |
|---|---|---|
| `created` | `{title, assignee}` | task appears as `todo` |
| `started` | `{}` | task → `doing` |
| `blocked_on` | `{reason, dependency?}` | task → `stuck` (flag + reason) |
| `unblocked` | `{note?}` | task → back to `doing` |
| `progress` | `{note, pct?}` | activity timestamp refresh |
| `artifact_published` | `{url, kind}` | task → `review`; marks deliverable |
| `done` | `{summary}` | task → `done` |
| `cancelled` | `{reason}` | task → `cancelled` |
| `heartbeat` | `{}` | agent liveness (stale after 5 min) |

## Status Derivation (query, not state)

```
done        ⇐ has artifact_published or done event
stuck       ⇐ latest event is blocked_on (and no unblocked after)
doing       ⇐ has started, no done, heartbeat < 5 min old
todo        ⇐ created only
```

## Commander UI (pulse screen)

- **Band 1 — Running:** tasks with active heartbeat.
- **Band 2 — Stuck:** tasks with `blocked_on` as latest; rollup by reason ("3 stuck, 2 same cause").
- **Band 3 — Done today:** tasks completed in last 24h.
- Each row: short title, owner, age, color dot. One-tap nudge (re-ping agent) / reassign.

## Idempotency & Races (Michelle's #1 risk)

- Client generates `event_id` (uuid) per event; server rejects duplicates (UNIQUE constraint).
- Appends are idempotent: retry-safe.
- Projections rebuildable from log — no mutable state drift.

## Non-Goals (hard-blocked feature creep)

- No message bus, no microservices, no RBAC, no org charts, no nested epics, no watchdog/QA gate chains, no invite→approve dance.

## Onboarding Flow

```
agent host:  curl -X POST convoy/api/register -d '{agent_id, name, capabilities, endpoint}'
             → {agent_id, secret}   (one command, one response)
agent host:  probe: POST /api/events {event_id, type:"heartbeat"} → 202  (live check)
commander:   GET /api/agents → sees agent GREEN
```

## Directory Layout

```
convoy/
├── README.md
├── docs/
│   ├── co-design-session.md
│   └── technical-design.md     (this file)
├── server/
│   ├── main.py                 (FastAPI app)
│   ├── models.py
│   └── derive.py               (status projection)
└── agent/
    └── convoy-agent.sh         (agent-side join + report helper)
```
