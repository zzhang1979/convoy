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

## Sprint 2 — (draft)

- S1.8 README quickstart (Jasmine)
- S2.1 Agent SDK: proper Python client lib (not just shell script)
- S2.2 UI: static file serving + auth flow polish
- S2.3 Docker deployment (Dockerfile + compose)
- S2.4 Event replay/rebuild test (projection integrity)
- S2.5 Multi-host agents (Hermes/OpenClaw integration proof)

## Definition of Ready (story is ready when)

- Acceptance criteria written · owner assigned · dependencies known.
