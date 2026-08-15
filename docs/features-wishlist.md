# Convoy — Feature Wish List (v1)

> **Document is king.** Every wish below is tracked with an ID so we can follow
> up on feature requests and bug reports. Statuses: `wish` → `planned` →
> `in-progress` → `done`. Priority: P0 (blocker) / P1 (high) / P2 (medium) / P3 (nice).
>
> Proposed 2026-08-14 by Anthony (commander). Design notes by Jean (leader).

## How to use this document
- Each item has a stable ID (`W1`, `W2`, …) — reference it in commits, bugs,
  and sprint stories.
- When a wish becomes a sprint story, mark it `planned` and link the sprint.
- When shipped, mark `done` with the commit/version.

---

## W1 — Work-item drill-down (granular detail per work item)
- **Status**: wish · **Priority**: P1 · **Owner**: TBD
- **What**: Click any work item on the pulse board → detail view showing:
  - full event history (who did what, when, in what order)
  - KV context (decisions, gotchas, wip_context)
  - artifacts produced (URLs) with timestamps
  - current status derivation trace (why is it Running/Stuck/Done)
- **Why**: Commander wants granular visibility into what each agent actually did.
- **Data**: already exists (events + KV + handoffs) — only a UI view + a
  `GET /api/tasks/{id}/timeline` endpoint needed.
- **Depends on**: nothing.

## W2 — Work items grouped by project
- **Status**: wish · **Priority**: P1 · **Owner**: TBD
- **What**: Tasks belong to a `project` (e.g. `convoy`, `gpsnet`, `leviandco-site`).
  Board and reports can be filtered/grouped by project.
- **Why**: Anthony runs multiple products; wants per-project tracking.
- **Design**: add `project` to task creation payload; store in events
  (`payload.project`) + derive into board query; UI gets a project filter/dropdown.
- **Data**: event payload already free-form — additive change only.
- **Depends on**: nothing.

## W3 — Artifact documentation search
- **Status**: wish · **Priority**: P1 · **Owner**: TBD
- **What**: Full-text search across artifact docs stored in KV (notes, SOP,
  handoff docs, user stories). `GET /api/search?q=...` returning matching
  artifacts with snippet + link.
- **Why**: "Document is king" — docs are the record for feature/bug follow-up;
  must be findable.
- **Design**: SQLite FTS5 virtual table over KV values + artifact payloads;
  index on write; simple relevance ranking.
- **Depends on**: W5 (docs as first-class artifacts) for good coverage.

## W4 — Role + agent attribution on work items
- **Status**: wish · **Priority**: P2 · **Owner**: TBD
- **What**: Every work item shows which **role** and which **agent** was on it
  (e.g. "engineer · michelle"), including role at the time of each event (roles
  can change over time).
- **Why**: Need to know who/what covered a task for review & cost attribution.
- **Design**: events already store `agent_id`; join with schedules for role;
  snapshot role in event payload at write time for historical accuracy.
- **Depends on**: nothing (mostly presentation).

## W5 — Task relationships (hyperlinks between work items)
- **Status**: wish · **Priority**: P2 · **Owner**: TBD
- **What**: Tasks can link to each other: `relates_to`, `blocks`,
  `duplicates`, `parent/child`. UI renders clickable links on the detail view
  for jumping to the related task for review.
- **Why**: Review flow needs to hop between related work items.
- **Design**: `task_links` table (from_task, to_task, kind); event type
  `task_linked`; UI shows link chips.
- **Depends on**: W1 (drill-down is where links render).

## W6 — User stories as first-class artifacts
- **Status**: wish · **Priority**: P1 · **Owner**: TBD
- **What**: Standard user-story template stored as an artifact per work item:
  `As a <role>, I want <capability>, so that <benefit>` + acceptance criteria.
  Stories appear in drill-down and are searchable.
- **Why**: User stories drive project tracking; Anthony explicitly wants them
  as artifacts.
- **Design**: KV namespace `task:<id>/user_story`; SOP rule: every new task
  gets a story; UI renders it in the detail view.
- **Depends on**: W1 (display), W3 (search).

---

## Backlog summary

| ID | Feature | Pri | Status |
|----|---------|-----|--------|
| W1 | Work-item drill-down | P1 | wish |
| W2 | Group by project | P1 | wish |
| W3 | Artifact search (FTS5) | P1 | wish |
| W4 | Role+agent attribution | P2 | wish |
| W5 | Task hyperlinks/relations | P2 | wish |
| W6 | User stories as artifacts | P1 | wish |

**Next step**: pick wishes into the next sprint planning (Anthony prioritizes;
Jean sequences; Jasmine/Michelle implement).

---
*Feature wish list v1 — 2026-08-14. Add new wishes at the bottom with a new W-number.*
