# Convoy Sprint Backlog

> **Team**: Jean (lead/Scrum Master/PO) · Jasmine (UX/design) · Michelle (engineering)
> **Workspace**: LXC u25-convoy @ 192.168.0.154 · `/workspace/convoy`
> **Repo**: https://github.com/zzhang1979/convoy
> **Process**: Agile — sprint planning → daily sync via A2A → review/retro at sprint end

## How We Work

1. **Sprint planning**: Jean decomposes the goal into stories, assigns owners.
2. **Story states**: `todo → in_progress → in_review → done` (in this doc, updated by whoever moves it).
3. **Daily sync**: quick A2A round — each agent reports: what I did / what's blocking me / what I'll do next.
4. **Commits**: to the shared repo, branch per story (`feat/<story>`), PR to main.
5. **Blocked?** Write it in the story, ping Jean. No watchdog chains — just say it.
6. **Definition of done**: code merged + basic verification + owner says done.

## Sprint 1 — Convoy MVP (event-log core) ✅ COMPLETE

**Goal**: Working MVP — server with append-only event log + REST intake + derived status views, agent onboarding via one command.

| # | Story | Owner | Status | Notes |
|---|-------|-------|--------|-------|
| S1.1 | Server skeleton: FastAPI app, SQLite `events` + `agents` tables, health endpoint | Michelle | ✅ done | Refactored (models.py split), merged |
| S1.2 | `POST /api/register` + `POST /api/events` (idempotent, event_id dedupe) | Michelle | ✅ done | Idempotent dedupe verified |
| S1.3 | Status derivation module (`derive.py`: done/stuck/doing/todo from events) | Jean | ✅ done | Facts-not-states projection |
| S1.4 | Commander pulse API: `GET /api/board` (running/stuck/done-today) | Jean | ✅ done | Restored on refactored main |
| S1.5 | Agent onboarding helper script (`agent/convoy-agent.sh` — join + heartbeat + report) | Jean | ✅ done | |
| S1.6 | Commander pulse UI (single screen, 3 bands, minimal HTML/JS) | Jasmine | ✅ done | Premium CSS-var theme, pulse animation, token mgmt |
| S1.7 | Integration test: 3 agents register, work, report, board reflects reality | Michelle | ✅ done | 7 passed / 1 skipped |
| S1.8 | README update: quickstart (run server, join agent, see board) | Jasmine | ⏳ todo | Sprint 2 carry-over |

## Sprint 1 Retrospective (filled by Jean as lead)

- **What went well**: Parallel branches worked; Michelle's refactor + Jasmine's UI merged cleanly (-X theirs). Tests caught the missing-functions gap (TDD win). Shared LXC + SSH keys = frictionless collaboration.
- **What to improve**: 
  1. **Branch hygiene** — commits landed on unexpected branches (s1.6 got s1.1 work); always `git branch --show-current` before commit.
  2. **A2A timeouts** — long prompts time out; keep A2A messages short, use the shared repo for details.
  3. **Finish what you start** — Michelle's refactor was incomplete (missing models funcs); tests were the safety net. Lead had to complete it.

## Sprint 2 — SOP, KV Store, Handoff & OpenClaw Support ✅ COMPLETE

**Goal**: Make Convoy a *self-documenting collaboration system* — new agents
onboard and pick up WIP tasks without asking. SOP is enforced by the system,
context travels via KV pairs, and handoffs are first-class events.

| # | Story | Owner | Status | Notes |
|---|-------|-------|--------|-------|
| S2.1 | **KV Store API** — `kv_store` table, PUT/GET by namespace+key, prefix search, agent-scoped writes | Jean | ✅ done | Verified: CRUD + permissions |
| S2.2 | **Handoff mechanism** — `handoff_requested` events, POST /api/tasks/{id}/handoff, WIP timeline shows handoffs | Jean | ✅ done | New agent sees WIP at registration |
| S2.3 | **SOP built-in** — `sop_rules` table + GET /api/sop, returned at registration | Jean | ✅ done | 7 default rules seeded |
| S2.4 | **OpenClaw adapter** — `agent/convoy-openclaw.sh` (curl-based join/report/handoff) + doc | Jean | ✅ done | CT107 agent joined successfully |
| S2.5 | **Python SDK** — `agent/convoy_sdk.py` (register, event, kv, handoff helpers) | Jean | ✅ done | |
| S2.6 | **Integration tests** — KV CRUD, handoff flow, SOP delivery | Jean | ✅ done | 13 passed total |
| S2.7 | **UI: handoff & KV visibility** — show handoff notes + KV context on task cards | Jasmine | ⏳ todo | Sprint 3 carry-over |

## Sprint 3 — Role-Based Costing & Agent Time Ranges ✅ COMPLETE

**Goal**: Track what each agent role costs and let the commander design
working time ranges per agent. Cost = active hours × role rate.

| # | Story | Owner | Status | Notes |
|---|-------|-------|--------|-------|
| S3.1 | **Roles + cost rates** — `roles` table (name, cost_per_hour), PUT /api/roles/{name} | Jean | ✅ done | Defaults: engineer 25, designer 30, qa 20, analyst 22, commander 0 |
| S3.2 | **Agent schedules** — `schedules` table (work_start, work_end, timezone, max_hours_per_day), PUT /api/agents/{id}/schedule | Jean | ✅ done | Michelle 07-15, Jasmine 12-20 |
| S3.3 | **Cost calculation API** — `GET /api/costs` aggregates active hours × role rate | Jean | ✅ done | Verified: 0.97h × $35 = $33.95 |
| S3.4 | **Cost + schedule in UI** — show per-agent cost, hours, working window | Jasmine | ⏳ todo | Sprint 4 |
| S3.5 | **Integration tests** — roles, schedules, cost math | Jean | ✅ done | 19 passed total |
| S3.6 | **Docker deployment** — Dockerfile + compose | Michelle | ⏳ todo | Sprint 4 |

## Sprint 4 — Token Usage + UI + Docker ✅ COMPLETE (usage core)

**Goal**: Track LLM token usage per agent (self-reported), fold token cost
into the costing model, ship remaining UI/Docker stories.

| # | Story | Owner | Status | Notes |
|---|-------|-------|--------|-------|
| S4.1 | **Token usage intake** — `usage` table, POST /api/usage (self-report) | Jean | ✅ done | Agents report after LLM calls |
| S4.2 | **Usage aggregation** — GET /api/usage (per agent/model, filters) | Jean | ✅ done | Verified: 430K+75K tok = $2.42 |
| S4.3 | **Token cost in costing** — roles get in/out per-1M pricing, /api/costs/full | Jean | ✅ done | Verified: time $33.95 + tokens $2.42 = $36.37 |
| S4.4 | **Cost + usage in UI** — pulse screen shows cost/hours/tokens/window | Jasmine | ⏳ todo | Sprint 5 |
| S4.5 | **Integration tests** — usage intake, aggregation, token math | Jean | ✅ done | 24 passed total |
| S4.6 | **Docker deployment** — Dockerfile + compose | Michelle | ⏳ todo | Sprint 5 |

**Note**: Simple path (self-report) done. Complex path (cross-platform auto-sync
via provider APIs) deferred to discussion — that's the "pair for later" item.

## Sprint 5 — Team-Ready: UI Serving, Docker, Onboarding ✅ DONE

**Goal**: Make Convoy usable by the whole team (Jean/Jasmine/Michelle) and
loggable by the commander — UI served, Docker deployable, onboarding docs.

| # | Story | Owner | Status | Notes |
|---|-------|-------|--------|-------|
| S5.1 | **UI static serving** — `/` and `/ui/` serve Jasmine's pulse screen | Jean | ✅ done | Commander logs in with token |
| S5.2 | **UI costs section** — per-agent hours/tokens/cost on pulse | Jean | ✅ done | refreshCosts() pulls /api/costs/full |
| S5.3 | **Docker deployment** — Dockerfile + compose, healthcheck | Jean | ✅ done | Smoke-tested on .108 |
| S5.4 | **Team quickstart** — docs/team-quickstart.md for all 3 agents | Jean | ✅ done | |
| S5.5 | **SDK role support** — ConvoyAgent(role=...) auto-schedules | Jean | ✅ done | Full team loop verified |
| S5.6 | **Old-DB migration** — ALTER roles + usage table on startup | Jean | ✅ done | No data loss on upgrade |

**Verified end-to-end**: Jasmine creates task → KV + usage → handoff to Michelle
→ Michelle sees WIP at registration → accepts → progresses. Commander views
board + costs/full from UI at http://192.168.0.154:8000/.

## Sprint 6 — Test Run: Team Works Through Convoy 🔄 IN PROGRESS

**Goal**: Real test run — Jasmine + Michelle pick up real tasks through Convoy
(register → events → KV → handoff), Anthony tracks via UI.

| # | Story | Owner | Status | Notes |
|---|-------|-------|--------|-------|
| S6.1 | **README quickstart** — clone, run server, join agent, see board | Jasmine | ✅ done | Rewrote quickstart (venv, SDK join/report, Docker alt); added missing `requests` dep |
| S6.2 | **Docker healthcheck polish** — compose `depends_on` + startup wait | Michelle/Antigravity | ✅ done | Fixed deadlock: run server in background during health checks |
| S6.3 | **Multi-host agent proof** — one agent reports from a non-.154 host | Michelle | 🔵 assigned | OpenClaw already done; do Hermes |
| S6.4 | **UI polish** — cost panel styling per Jasmine's design taste | Jasmine | ✅ done | Cost grid: role chips, tabular nums, totals row, mobile collapse, XSS-safe render |

**Test-run protocol**: both agents register via SDK, report via events, use KV
for context, hand off if switching. Anthony watches the board live.

## Feature Wish List (from Anthony, 2026-08-14)

**Document is king.** Full details + tracking in **[docs/features-wishlist.md](docs/features-wishlist.md)**.
IDs referenced in commits/bugs/sprints.

| ID | Feature | Pri | Status |
|----|---------|-----|--------|
| W1 | Work-item drill-down (granular detail per task) | P1 | ✅ done (Sprint 7) |
| W2 | Work items grouped by project | P1 | ✅ done (Sprint 7) |
| W3 | Artifact documentation search (FTS5) | P1 | ✅ done (Sprint 8) |
| W4 | Role + agent attribution on work items | P2 | ✅ done (Sprint 7) |
| W5 | Task relationships (hyperlinks for review) | P2 | ✅ done (Sprint 8) |
| W6 | User stories as first-class artifacts | P1 | ✅ done (Sprint 7) |

## Sprint 8 — Wish List: Search + Task Links ✅ DONE

**Goal**: Ship W3 (FTS5 artifact search) + W5 (task relationships).

| # | Story | Owner | Status | Notes |
|---|-------|-------|--------|-------|
| S8.1 | **W3: FTS5 search** — `search_idx` virtual table, `/api/search?q=`, backfill script | Jean | ✅ done | 32 tests passed |
| S8.2 | **W5: Task links** — `task_links` table, POST/GET `/api/tasks/{id}/links` | Jean | ✅ done | relates_to/blocks/duplicates/parent |
| S8.3 | **UI** — search box + results panel + link chips in drill-down | Jean | ✅ done | click result → drill |

**Sprint 7 — Wish List: Drill-down, Projects, Roles, User Stories ✅ DONE**

**Goal**: Ship Anthony's wish list items W1/W2/W4/W6 — granular visibility,
project grouping, role attribution, user-story artifacts.

| # | Story | Owner | Status | Notes |
|---|-------|-------|--------|-------|
| S7.1 | **W2: Project grouping** — tasks get `project`, board filters by project | Jean | ✅ done | `?project=` + UI dropdown |
| S7.2 | **W6: User-story artifacts** — SOP rule + KV template, shown in detail | Jean | ✅ done | `task:<id>/user_story` |
| S7.3 | **W1: Task drill-down** — `GET /api/tasks/{id}/timeline` + UI detail view | Jean | ✅ done | events+KV+artifacts+story |
| S7.4 | **W4: Role attribution** — snapshot role on events, show in board+detail | Jean | ✅ done | historical accuracy |
| S7.5 | **Tests + deploy + docs** | Jean | ✅ done | 29 passed |

## Sprint 9 — OpenClaw Containers + Token Hygiene + Agent Permissions 🔄 IN PROGRESS

**Goal**: Bring the Dockerized Henry instances back into the loop, fix the
multi-bot token conflict, and close the agent-permission gap Henry flagged.

| # | Story | Owner | Status | Notes |
|---|-------|-------|--------|-------|
| S9.1 | **Henry containers health** — diagnose henry2-fresh/henry3 unhealthy, TG poller conflict (shared bot token) | Jasmine | 🔵 planned | each container needs its OWN bot token or webhook mode |
| S9.2 | **Agent read-only view** — agents can GET /api/board + /api/tasks/{id} with their own token (Henry hit 403) | Jean/Antigravity | ✅ done | read-scoped auth, no write escalation |
| S9.3 | **Henry SDK rebuild** — re-save convoy_sdk.py + token into henry1 container (lost on containerization) | Jasmine/Henry | 🔵 planned | verify heartbeat + event send from container |
| S9.4 | **New agent onboarding doc** — antigravity/QA agent join via OpenAI Agents SDK (R-1 pilot) | Jean/Antigravity | ✅ done | Pilot agent implemented at agent/qa_agent_pilot.py and doc at docs/antigravity-qa-onboarding.md |

## Sprint 10 — QA Pilot + Observability + Hardening 🚀 PLAN

**Goal**: Stand up the R-1 recommended QA agent (OpenAI Agents SDK) and
harden Convoy for the antigravity handoff.

| # | Story | Owner | Status | Notes |
|---|-------|-------|--------|-------|
| S10.1 | **QA agent pilot** — OpenAI Agents SDK agent, joins Convoy, runs a real review task | Jean | 🔵 planned | measure tokens vs baseline (R-1) |
| S10.2 | **Token/usage dashboard** — per-agent token burn chart in UI (we track costs) | Jasmine | 🔵 planned | from /api/costs/full |
| S10.3 | **Stale-task detection** — heartbeat-based stale flag (running tasks with old hb) | Jean | 🔵 planned | mark-done question from Anthony |
| S10.4 | **Antigravity onboarding pack** — README for new collaborators: repo map, event model, SDK, test recipe, deploy recipe | Jean | 🔵 planned | for stonechueng@gmail.com |

## Definition of Ready (story is ready when)

- Acceptance criteria written · owner assigned · dependencies known.
