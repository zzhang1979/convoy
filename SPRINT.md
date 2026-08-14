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

## Sprint 1 — Convoy MVP (event-log core)

**Goal**: Working MVP — server with append-only event log + REST intake + derived status views, agent onboarding via one command.

| # | Story | Owner | Status | Notes |
|---|-------|-------|--------|-------|
| S1.1 | Server skeleton: FastAPI app, SQLite `events` + `agents` tables, health endpoint | Michelle | done | verified locally (pytest + uvicorn); branch feat/s1.1-server-skeleton, push pending LXC sshd |
| S1.2 | `POST /api/register` + `POST /api/events` (idempotent, event_id dedupe) | Michelle | done | verified locally (pytest + uvicorn); branch feat/s1.1-server-skeleton, push pending LXC sshd |
| S1.3 | Status derivation module (`derive.py`: done/stuck/doing/todo from events) | Jean | todo | |
| S1.4 | Commander pulse API: `GET /api/board` (running/stuck/done-today) | Jean | todo | |
| S1.5 | Agent onboarding helper script (`agent/convoy-agent.sh` — join + heartbeat + report) | Jean | todo | |
| S1.6 | Commander pulse UI (single screen, 3 bands, minimal HTML/JS) | Jasmine | todo | |
| S1.7 | Integration test: 3 agents register, work, report, board reflects reality | Michelle | in_progress | 7/8 pass locally; board assertion skips until S1.4 lands; push pending LXC sshd |
| S1.8 | README update: quickstart (run server, join agent, see board) | Jasmine | todo | |

## Sprint 2 — (draft)

- Multi-agent concurrency tests, event replay/rebuild, auth hardening (shared secret), Docker deployment.

## Definition of Ready (story is ready when)

- Acceptance criteria written · owner assigned · dependencies known.

## Retrospective (end of Sprint 1)

- (to be filled)
