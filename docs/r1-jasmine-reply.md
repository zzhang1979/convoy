Fetched the brief from origin/main and evaluated from the designer/process seat. Direct reply:

---

**Framework research — Jasmine (designer/process)**

**Q1 — Fits the event-log philosophy:** None natively *is* an append-only log, but OpenAI Agents SDK and Mastra model *transitions*, not truth — they complement Convoy instead of competing. Keep the event log as source of truth; frameworks only orchestrate inside an agent.

**Q2 — Token discipline:** OpenAI Agents SDK. Handoffs carry explicit payloads with zero ambient context — leader→designer→engineer→QA maps 1:1 to its handoff primitive. LangGraph's pruning is strong but its centralized state object invites carrying everything. CrewAI needs Flows (extra machinery) just to reach "medium" control.

**Q3 — Incremental join:** OpenAI Agents SDK again: a new agent runs it internally and emits events to Convoy via the existing HTTP SDK — zero changes for Jean/Henry. CrewAI's roles match ours conceptually but it's the heaviest bolt-on.

**Q4 — Would replace the log:** LangGraph is the risk — its state object wants to *be* the source of truth; resisting that is daily friction. CrewAI's hierarchical process also owns workflow state. OpenAI Agents SDK and Mastra are stateless enough to stay passengers.

**Q5 — Ranked for us** (Python-heavy, Hermes+OpenClaw mix, $3/$15 per M tokens):
1. **OpenAI Agents SDK** — Python, minimal, explicit handoffs, no persistence claims. Best fit now.
2. **LangGraph** — powerful, but only with hard discipline that Convoy stays authoritative; graph-first thinking fights our log-first thinking.
3. **Mastra** — clean typed pipelines, but TS-only; relevant only if the TS side hosts agents.
4. **AutoGen** — message filtering helps, but its mental model is chat rooms, not handoffs.
5. **CrewAI** — role names match, but token discipline is "medium (needs Flows)" — you pay complexity for control.

**Recommendation:** pilot OpenAI Agents SDK on one new agent (QA) beside Henry — no Convoy changes, and we get a measurable per-handoff token delta against the current SDK path.