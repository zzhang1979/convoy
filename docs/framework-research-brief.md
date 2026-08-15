# Framework Research Brief — Convoy Agent Team (R-1)

Anthony's pain points with Paperclip: **token inflation + context overhead**
(agents passing full chat histories / verbose system prompts back and forth).

Candidate frameworks to evaluate for our agent team setup:

| # | Framework | Paradigm | State Mgmt | Token Control | Stack |
|---|-----------|----------|-----------|---------------|-------|
| 1 | LangGraph | Directed Graph | Centralized State Object | High (state pruning) | Python/TS |
| 2 | AutoGen / MS Agent Framework | Event/Message-driven | Message History Filtering | Med-High (context rules) | Python/.NET |
| 3 | Mastra | Workflows & Graphs | Typed Step Pipelines | High (explicit payloads) | TypeScript |
| 4 | OpenAI Agents SDK | Handoff Primitives | Explicit Handoff Payloads | High (zero overhead) | Python |
| 5 | CrewAI | Role-based Teams | Hierarchical/Sequential | Medium (needs Flows) | Python |

## Our current team setup (context for evaluation)

- **Convoy**: self-built orchestration (append-only event log = source of truth;
  status derived by query; agents register + report events via HTTP SDK).
- **Agents**: Jean (Hermes, leader/commander), Jasmine (Hermes, designer),
  Henry (OpenClaw, engineer), Michelle (offline).
- **Cost model**: active hours × role rate + token costs ($3/1M in, $15/1M out).
  Token efficiency = real money.
- **Constraints**: single FastAPI process, SQLite; A2A links between Hermes
  instances; OpenClaw participates via its own gateway.

## Evaluation questions (answer these)

1. Which framework fits our **append-only event log / derived-state** philosophy
   without forcing us to rebuild Convoy around its abstractions?
2. Which gives the **strongest token discipline** for a team where agents
   hand work to each other (leader → designer → engineer → QA)?
3. Which is **easiest to integrate incrementally** — could a NEW agent join
   using it while existing agents stay on Convoy SDK?
4. Any framework whose mental model would **replace Convoy's event log**
   rather than complement it? (We prefer keeping the event log.)
5. Given our stack (Python-heavy, one TypeScript app, Hermes + OpenClaw mix),
   rank the 5 for OUR situation, not in the abstract.

## Your angle (Jasmine)

You are the designer + team-process thinker. Evaluate from: (a) how a
designer/QA agent would experience each framework day-to-day, (b) token
spend realism for a small team, (c) which framework's workflow matches how
we already work (event log, handoffs, artifacts).

Keep your reply under 300 words. Reply as a colleague, structured, concrete.
