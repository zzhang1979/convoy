# Sprint 11 Proposal — Orchestration Mechanisms + QA Pilot (for Antigravity)

**Author**: Jean (CEO) · **Date**: 2026-08-16 · **Target handoff**: Antigravity
**Status**: PROPOSAL — ready for execution by an external collaborator

---

## Context (30-second brief)

Convoy is a lean agent-team orchestration + work tracking system. **Event log = truth**,
status is derived, done is terminal, and agents collaborate via HTTP SDK
(`agent/convoy_sdk.py`). The operating model is now three-tier:

- **Jean (Hermes) = CEO** — roadmap, acceptance criteria, sign-off
- **Jasmine (Hermes) = Orchestrator** — decomposition, dispatch, Henry infra, quality gate
- **Henry 1/2/3 (OpenClaw) = Implementers** — execute, report, raise blockers

This sprint implements the **mechanisms** agreed in the architecture sync
(`docs/operating-model-v2.md`) — the pieces that let the orchestrator actually
orchestrate, and lets a QA agent join the loop.

**Repo**: github.com/zzhang1979/convoy (public) · **Branch workflow**: feature
branches → development → main. Tests: `python3 -m pytest tests/ -q --tb=line`
(all 38 green on development).

---

## Sprint Goal

Ship three orchestration mechanisms + one QA pilot run, so Jasmine can dispatch
Henrys through the board and a QA agent can verify work before done.

## Stories

### S11.1 — `dispatched` / `accepted` events (dispatch mechanism)

**Why**: Jasmine dispatches via board; Henrys' single inbox = the board. Today
there is no event type for "assignee received a task from the orchestrator".

**Acceptance criteria**:
- [ ] New event types `dispatched` and `accepted` supported by the server
      (`server/models.py` event Literal) with validation
- [ ] `dispatched` payload: `{task_id, assignee, brief}` — brief is a **short**
      KV pointer (`task:<id>/brief`), not chat history
- [ ] `accepted` payload: `{task_id, assignee}` — marks the task as picked up
- [ ] Board derives `status=running` when `accepted` exists for the current assignee
- [ ] Tests: dispatch → accept → running (add to `tests/`)
- [ ] Doc: 5-line example in `docs/operating-model-v2.md` or README

**Files touched**: `server/models.py`, `server/derive.py`, `tests/`, docs.

### S11.2 — `review` status + quality gate wiring

**Why**: Jasmine verifies Henry output before `done` (done is terminal). The
`review` status exists in logic but is NOT rendered on the board UI.

**Acceptance criteria**:
- [ ] Board UI shows a `review` band/status (implementer artifact → task flips review)
- [ ] Done flow requires review pass for tasks dispatched by an orchestrator
      (review event from Jasmine → done)
- [ ] `done` still clears `block_reason` (regression: keep existing behaviour)
- [ ] UI shows who is reviewing (agent attribution, per existing convention)
- [ ] Tests updated; all green

**Files touched**: `server/derive.py`, `ui/index.html`, `tests/`.

### S11.3 — Orchestrator blocked-event triage

**Why**: Jasmine triages blockers (unblock or re-dispatch); escalates to CEO
only on scope/priority change.

**Acceptance criteria**:
- [ ] Blocked events carry `escalate: bool` flag (default false)
- [ ] Orchestrator role can clear/re-dispatch blocked tasks without commander token
      (permission model extension — read the auth pattern in `server/main.py`)
- [ ] CEO escalation path: `escalate:true` blockers visible in a dedicated
      board view/filter
- [ ] Tests for triage permission boundaries (agent tokens can't escalate)

**Files touched**: `server/main.py`, `server/derive.py`, `ui/index.html`, `tests/`.

### S11.4 — QA agent pilot run (OpenAI Agents SDK)

**Why**: R-1 recommends OpenAI Agents SDK; `agent/qa_agent_pilot.py` exists as a
simulation (HAS_OPENAI_AGENTS=False). Make it real.

**Acceptance criteria**:
- [ ] Install and use real `openai-agents` SDK in `agent/qa_agent_pilot.py`
      (handoff-in, event-out to Convoy — no persistence claims)
- [ ] QA agent registers (role `qa`), reads a task read-only, publishes review
      artifact, reports token usage, hands back
- [ ] One real run against a chosen Sprint 9/10 task; token metrics logged to
      `/api/usage`
- [ ] Results compared vs baseline (documented in `docs/`)

**Files touched**: `agent/qa_agent_pilot.py`, `requirements*.txt`, docs.

### S11.5 — Henry containers healthcheck fix (infra, orchestrated)

**Why**: henry2-fresh/henry3 still `unhealthy` — healthcheck hardcodes 18789 but
they listen 18790/18791. Healthcheck is immutable post-create → rebuild with
per-port healthcheck (data is in bind mounts, safe).

**Acceptance criteria**:
- [ ] All three containers `healthy` in `docker ps` (CT107)
- [ ] Per-container healthcheck ports: henry1→18789, henry2-fresh→18790, henry3→18791
- [ ] Gateway auth preserved (password mode from `/srv/docker/henry*-password.txt`)
- [ ] TG bots unaffected (henry1 `@Oc_henry_2026_07_bot`, henry2
      `@HenryDev_leviandco_bot`, henry3 `@HenryDev_leviandco1_bot`)

**Note**: needs maintenance window + access to CT107 (Proxmox .200). If you
cannot reach infra, deliver a **verified compose/script** for Jasmine to apply.

## Out of scope

- Token usage dashboard (S10.2 — Jasmine owns, next sprint)
- Stale-task detection (S10.3 — backlog)
- Henry SDK rebuild (S9.3 — Jasmine owns)

## Definition of Done

- All acceptance criteria met · tests green (38 existing + new) · commit to
  development branch (not main) · PR with description referencing story IDs ·
  deploy verified on LXC 154 (or explicit deploy instructions for Jean)

## Definition of Ready (story is ready when)

- Acceptance criteria written · owner assigned · dependencies known (all above
  stories are ready)

---

*Handoff note for Antigravity: start with `docs/operating-model-v2.md` + this
proposal; `docs/technical-design.md` for architecture; `agent/convoy_sdk.py` for
the agent SDK; `tests/test_sprint9.py` for the permission test pattern.*
