# R-1 Research Findings — Orchestration Framework for the Convoy Team

**Date**: 2026-08-15 · **Researchers**: Jean (leader) + Jasmine (designer/process)
**Question**: Which framework best fits OUR agent team (token efficiency + event-log philosophy)?

## Verdict (Jean + Jasmine consensus)

**OpenAI Agents SDK is the best fit for our setup.** Runner-up: LangGraph (only with strict discipline). Mastra is excellent but TypeScript-only — relevant only if the TS side hosts agents.

## Why OpenAI Agents SDK (agreed by both)

| Criterion | Fit |
|---|---|
| **Token discipline** | Handoffs carry **explicit payloads, zero ambient context** — leader→designer→engineer→QA maps 1:1 to its handoff primitive. No chat-history passing. |
| **Fits event-log philosophy** | Stateless transitions — it models *handoffs*, not *truth*. **Convoy stays the source of truth**; SDK is a passenger. |
| **Incremental join** | A new agent runs SDK internally + emits events to Convoy via existing HTTP SDK. **Zero changes for Jean/Henry/Convoy.** |
| **Stack** | Python-native (≥3.10), minimal deps, v0.21 active. No heavy runtime. |
| **Risk** | None to Convoy — it claims no persistence, no global state. |

## The 5 ranked for OUR situation

1. **OpenAI Agents SDK** — Python, minimal, explicit handoffs, no persistence claims. Best fit now.
2. **LangGraph** — most powerful, BUT its centralized state object wants to *be* the source of truth — daily friction against our log-first thinking. Token control only with hard state pruning discipline.
3. **Mastra** — clean typed pipelines (Zod schemas, step functions), but TS-only. Only if the TS side hosts agents.
4. **AutoGen/AG2** — event-driven v0.4 is solid, message filtering helps, but its mental model is chat rooms, not handoffs; AutoGen now in maintenance mode (MS shifted to Agent Framework).
5. **CrewAI** — role names match ours (Researcher→Writer→Editor), but token discipline is "medium (needs Flows)" — you pay complexity for control. Heaviest bolt-on.

## Jasmine's key insight (verbatim)

> "OpenAI Agents SDK and Mastra model *transitions*, not truth — they complement Convoy instead of competing. Keep the event log as source of truth; frameworks only orchestrate inside an agent."

> "LangGraph is the risk — its state object wants to *be* the source of truth; resisting that is daily friction."

## Recommendation & next step

**Pilot OpenAI Agents SDK on one new agent (QA) beside Henry.** No Convoy changes, no event-log replacement:
1. Spin up a QA agent using OpenAI Agents SDK (handoff-in, event-out to Convoy).
2. Measure token spend vs an equivalent CrewAI/LangGraph run on the same task.
3. If the pilot beats baseline, standardize new agents on it.

## Comparison table

| Platform | Paradigm | State Mgmt | Token Control | Stack | Fits our log? |
|---|---|---|---|---|---|
| **OpenAI Agents SDK** | Handoff primitives | Explicit payloads | **High (zero overhead)** | Python | ✅ passenger |
| LangGraph | Directed graph | Centralized state obj | High (needs pruning) | Python/TS | ⚠️ wants to be truth |
| Mastra | Workflows & graphs | Typed pipelines | High (explicit) | **TS only** | ✅ passenger (TS caveat) |
| AutoGen/AG2 | Event-driven | Msg history filtering | Med-High | Python/.NET | ⚠️ chat-room mental model |
| CrewAI | Role-based teams | Hierarchical/Sequential | Medium (needs Flows) | Python | ⚠️ heaviest bolt-on |
