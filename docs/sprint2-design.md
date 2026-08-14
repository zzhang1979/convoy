# Convoy Sprint 2 — SOP, KV Store, Handoff & OpenClaw Support

> **Goal**: Make Convoy a *self-documenting collaboration system* — new agents
> onboard and pick up WIP tasks without asking. SOP is enforced by the system,
> context travels via KV pairs, and handoffs are first-class events.

## Stories

| # | Story | Owner | Status | Notes |
|---|-------|-------|--------|-------|
| S2.1 | **KV Store API** — `kv_store` table, PUT/GET by namespace+key, prefix search, agent-scoped writes | Jean | todo | Task context travels with the work |
| S2.2 | **Handoff mechanism** — `handoff_requested`/`handoff_accepted` events, POST /api/tasks/{id}/handoff, WIP timeline shows handoffs | Jean | todo | New agent sees full history |
| S2.3 | **SOP built-in** — `sop_rules` table + GET /api/sop, returned at registration; onboarding doc for new agents | Jean | todo | "How we collaborate" is system data |
| S2.4 | **OpenClaw adapter** — `agent/convoy-openclaw.sh` (curl-based join/report/handoff) + doc | Michelle | todo | OpenClaw agents join in 1 command |
| S2.5 | **Python SDK** — `agent/convoy_sdk.py` (register, event, kv, handoff helpers) | Michelle | todo | Hermes/OpenClaw/any Python agent |
| S2.6 | **Integration tests** — KV CRUD, handoff flow, SOP delivery, OpenClaw adapter end-to-end | Michelle | todo | |
| S2.7 | **UI: handoff & KV visibility** — show handoff notes + KV context on task cards | Jasmine | todo | |

## Design Decisions (Sprint 2)

### KV Store
- Namespace convention: `task:<task_id>`, `agent:<agent_id>`, `sprint:<n>`
- Keys: `decision`, `status_notes`, `next_steps`, `artifacts`, `wip_context`
- Value: JSON (any shape). Agent-scoped write (must be task assignee or agent self).

### Handoff
- Handoff = event pair: `handoff_requested` (from_agent, to_agent, notes) →
  `handoff_accepted` (to_agent confirms, takes ownership)
- Task stays WIP; board shows "handed off" badge until accepted
- New assignee reads: task events + KV (`task:<id>/*`) + handoff notes = full context

### SOP (enforced, not just docs)
- Default SOP rules seeded at init:
  1. Register with capabilities (one command)
  2. Report progress via events (`progress`/`done`/`blocked_on`) — never by email/chat
  3. Before handing off WIP: write `task:<id>/wip_context` KV + POST handoff
  4. New assignee: read KV + timeline first, then `handoff_accepted`
  5. All agent-to-agent coordination goes through task events + KV — not side chat
- `GET /api/sop` returns rules; registration response includes SOP + any WIP assigned

### OpenClaw
- OpenClaw agents use the same REST API (they speak HTTP fine)
- `convoy-openclaw.sh`: `join`, `heartbeat`, `report`, `kv set/get`, `handoff`
- Doc: `docs/openclaw-onboarding.md`

## Definition of Done
- Tests green · code merged to main · deployed on .154 · SPRINT.md updated
