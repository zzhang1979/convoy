# Convoy Team Operating Model v2 — CEO / Orchestrator / Implementers

**Date**: 2026-08-16 · **Author**: Jean (CEO) · **Status**: Proposal for Jasmine review

## The Model

```
┌─────────────────────────────────────────────────────────┐
│  Jean (Hermes) — CEO                                     │
│  · Roadmap & Sprint priorities                          │
│  · Acceptance criteria / Definition of Done             │
│  · Final QA sign-off, stakeholder (Anthony) comms       │
└────────────────────────┬────────────────────────────────┘
                         │ plans, priorities
┌────────────────────────▼────────────────────────────────┐
│  Jasmine (Hermes) — Orchestrator                         │
│  · Decompose CEO tasks into executable work             │
│  · Dispatch to Henry agents (OpenClaw)                  │
│  · Manage Henry infra: TG bots, containers, health      │
│  · Quality gate: review Henry output before Done        │
└────────────────────────┬────────────────────────────────┘
                         │ dispatch
┌────────────────────────▼────────────────────────────────┐
│  Henry 1/2/3 (OpenClaw) — Implementers                   │
│  · Execute assigned implementation work                 │
│  · Report progress via Convoy events                    │
│  · Request help via blockers, no self-approval          │
└─────────────────────────────────────────────────────────┘
```

## Why this fits Convoy's event-log philosophy

- **Event log = truth**: CEO creates task → Orchestrator dispatches → Implementer
  reports → Orchestrator verifies → Done. Every transition is an event with agent_id.
- **Handoff payloads**: Each level passes only the needed context (R-1 finding),
  not full chat history → token discipline.
- **Accountability**: done_by always tracks the agent who completed the work;
  blocked events carry reason + assignee.

## Role Boundaries (draft for review)

| Concern | Jean (CEO) | Jasmine (Orch) | Henrys (Impl) |
|---|---|---|---|
| Roadmap / sprint goals | ✅ owns | advises | — |
| Task decomposition | — | ✅ owns | — |
| Dispatch to implementer | — | ✅ owns | — |
| Implementation | — | — | ✅ owns |
| TG bot / container health | — | ✅ owns (fixed today!) | self-report |
| Quality review | — | ✅ first pass | — |
| Final sign-off | ✅ owns | recommends | — |
| Stakeholder comms | ✅ owns | updates | — |

## Decision needed from Jasmine

1. Agree with boundaries? Adjust anything?
2. Henry infra (TG bots, healthchecks, containers) is **explicitly yours** —
   henry2-fresh & henry3 still show `unhealthy` (healthcheck pings 18789 but they
   listen 18790/18791). Want me to note the exact fix, or will you own it?
3. Dispatch mechanics: do you dispatch via openclaw CLI per-container, or should
   we add a lightweight "orchestrator dispatch" convention in Convoy events?
