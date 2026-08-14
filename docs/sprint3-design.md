# Convoy Sprint 3 — Role-Based Costing & Agent Time Ranges

> **Goal**: Track what each agent role costs and let the commander design
> working time ranges per agent. Cost = active hours × role rate.

## Stories

| # | Story | Owner | Status | Notes |
|---|-------|-------|--------|-------|
| S3.1 | **Roles + cost rates** — `roles` table (name, cost_per_hour), agent registration accepts role, PUT /api/roles/{name} to configure | Jean | todo | Default rates: engineer 25, designer 30, qa 20, commander 0 |
| S3.2 | **Agent schedules** — `schedules` table (work_start, work_end, timezone, max_hours_per_day), PUT /api/agents/{id}/schedule | Jean | todo | Commander designs time ranges per agent |
| S3.3 | **Cost calculation API** — `GET /api/costs` aggregates active hours (from event log) × role rate, per agent + per role | Jean | todo | |
| S3.4 | **Cost + schedule in UI** — show per-agent cost, hours, and working window on pulse screen | Jasmine | todo | |
| S3.5 | **Integration tests** — role config, schedule CRUD, cost math | Jean | todo | |
| S3.6 | **Docker deployment** — Dockerfile + compose for the server | Michelle | todo | |

## Design Decisions

### Cost model
- `roles.cost_per_hour` — configured by commander (PUT /api/roles/{name})
- Agent inherits cost from its role; optional per-agent override in schedules
- Active hours derived from event log: sum of time spans between an agent's
  consecutive events (capped by max_hours_per_day), only counting hours inside
  the agent's work window (work_start → work_end, in its timezone)

### Schedule model
- `schedules` row per agent: work_start "09:00", work_end "17:00", tz "Australia/Melbourne", max_hours_per_day 8
- Default: 09:00-17:00 Australia/Melbourne, 8h/day
- Commander can design different windows per agent (e.g. night-owl agent 22:00-06:00)

### API
- PUT /api/roles/{name}  {cost_per_hour}
- GET /api/roles
- PUT /api/agents/{id}/schedule  {work_start, work_end, timezone, max_hours_per_day}
- GET /api/agents/{id}/schedule
- GET /api/costs  → per-agent {agent, role, hours, rate, cost} + per-role totals + grand total

## Definition of Done
- Tests green · merged to main · deployed on .154 · SPRINT.md updated
