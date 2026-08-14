# Convoy Co-Design Session — 2026-08-14

Participants: **Jean** (commander, orchestrator), **Jasmine** (designer, .234), **Michelle** (engineer, .211), **Anthony** (owner, final decision maker).

## Brief from Anthony

> Build a software development project to create a platform for the commander workflow: I am the commander, break down tasks, assign to Hermes or OpenClaw to work on, they report progress and issues, then I decide what to do. Reflect what Paperclip has and create a better one — keep it lean and easy for agent onboarding and task tracking.

## Jasmine's Design Perspective (verbatim excerpts)

**Lean commander UI:**
> One pulse screen, three bands: Running / Stuck / Done today. One row per item: short title, owner, age, single color dot. Status vocabulary ≤5 words (todo → doing → review → done); blocked is a flag with a reason, never a status — "stuck on Jasmine: missing Infisical token", not "status=blocked". Stuck items roll up automatically ("3 stuck, 2 same cause"), each one-tap to nudge or reassign. No Kanban mazes, no nested epics.

**Easy onboarding:**
> One command on the agent's own host: `agent join <company> --token`. It self-reports capabilities + endpoint, the platform probes connectivity/auth/one trivial task live, and shows green only when verified — no invite→join→approve→claim-key dance, no hand-edited adapterConfig, no ws:// vs http:// guesswork.

**Paperclip's three design sins:**
1. Status machines as truth — blocked is a harness artifact with no real dependency model. The UI lies. Model dependencies explicitly; derive status from them.
2. Escalation chains instead of surfaces — watchdog/QA gates spawn infinite recovery loops; the human sees noise, not signal. Escalate once, visibly, with what's actually missing.
3. Auth friction as architecture — per-agent keys, boundary 403s, board-only powers. Auth is a thin layer, not the product.

**MVP vision:**
> A single glass pane showing what the company is doing right now — derived truth, not agent-reported state — where any agent joins by one command, any blocker is one sentence with an owner, and the commander's only job is choosing what matters next.

## Michelle's Engineering Perspective (verbatim excerpts)

**MVP architecture:**
> One binary, one DB (Postgres; SQLite fine for single-node dev). No message bus, no microservices. Thin REST API: agents POST /events (JSON), server appends to an append-only event log, returns 202. Webhook-push only; polling is a fallback, not a first-class path. Everything else (status, boards, dashboards) is a read-model projection over the log, rebuildable at any time.

**Task tracking without a status machine:**
> Agree with Jasmine, fully. Store facts, not states: created, started, blocked_on(X), artifact_published(url). Derive status: done iff artifacts exist, blocked iff unsatisfied deps, in_progress iff an active lease/heartbeat. Status becomes a query — the impossible-transition bug class disappears because there's no transition table to violate.

**Onboarding:**
> POST /register with agent_id + capability manifest → per-agent secret. Report via webhook + heartbeat every ~2 min; server marks stale at 5. Auth = one shared-secret header, no users/roles/boards. Paperclip's complexity came from modeling an org chart into the tool; agents need capability admission, not RBAC.

**#1 risk:**
> Duplicates and races — agents retry, double-fire, and the log is the source of truth. Mitigate with client-supplied event_id dedupe keys, idempotent appends, and event-sourcing-lite so projections rebuild cleanly. #2: feature creep. Hard-block anything that isn't event-in → projection-out.

**MVP vision:**
> A tiny, boring core: append-only event log, REST intake, derived views. Agents join with one HTTP call, report with one header, and the "state machine" is just a query. Lean enough for a Raspberry Pi, honest enough to rebuild from the log. Weeks, not quarters.

## Consensus

- **Event log = source of truth; status = derived query.** (Both agree 100%)
- **Blocked = flag with reason, not status.**
- **One-command onboarding, capability-based admission, thin auth.**
- **Single binary, single DB, REST, webhook-push.**
- **Derived UI: Running / Stuck / Done today.**
