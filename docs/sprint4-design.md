# Convoy Sprint 4 — Token Usage Tracking + UI + Docker

> **Goal**: Track LLM token usage per agent (self-reported), fold token cost
> into the costing model, and ship the remaining UI/Docker stories.

## Stories

| # | Story | Owner | Status | Notes |
|---|-------|-------|--------|-------|
| S4.1 | **Token usage intake** — `usage` table (agent, task, model, in/out tokens, ts), POST /api/usage (self-report) | Jean | todo | Agents report after each LLM call |
| S4.2 | **Usage aggregation** — GET /api/usage (per agent/role, filters: task, since, model) | Jean | todo | |
| S4.3 | **Token cost in costing** — roles get `in_cost_per_1m`/`out_cost_per_1m`, /api/costs includes token $ | Jean | todo | Cost = time + tokens |
| S4.4 | **Cost + usage in UI** — show per-agent cost, hours, tokens, window on pulse screen | Jasmine | todo | |
| S4.5 | **Integration tests** — usage intake, aggregation, token cost math | Jean | todo | |
| S4.6 | **Docker deployment** — Dockerfile + compose for the server | Michelle | todo | |

## Design Decisions

### Self-report model (simple path)
- Agents call `POST /api/usage` after LLM calls: `{task_id?, model, tokens_in, tokens_out}`
- SDK/OpenClaw adapter get `usage()` helpers — one line per call
- Server stores rows; aggregation is pure SQL — no cross-platform scraping
- (Cross-platform auto-sync via provider APIs = complex path, deferred to discussion)

### Token cost model
- roles table gains `in_cost_per_1m`, `out_cost_per_1m` (USD)
- Token cost = tokens_in/1e6 × in_cost + tokens_out/1e6 × out_cost
- /api/costs total = time_cost + token_cost (both shown separately)

### Aggregation
- GET /api/usage → per-agent {agent, role, tokens_in, tokens_out, calls, token_cost}
- Filters: `task_id`, `since` (ISO), `model`, `agent_id`
