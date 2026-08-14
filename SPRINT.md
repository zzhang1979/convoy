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

## Sprint 3 — (draft)

- S2.7 UI handoff & KV visibility (Jasmine)
- S1.8 README quickstart (Jasmine)
- S3.1 Docker deployment (Dockerfile + compose)
- S3.2 Hermes kanban bridge (Hermes tasks → Convoy events)
- S3.3 Multi-host agents (Hermes/OpenClaw integration proof)
- S3.4 Event replay/rebuild test (projection integrity)

## Definition of Ready (story is ready when)

- Acceptance criteria written · owner assigned · dependencies known.
