# Onboarding Antigravity & QA Agent Pilot (OpenAI Agents SDK)

This guide details how to onboard and run the R-1 recommended QA pilot agent using the **OpenAI Agents SDK** (Swarm pattern) within the Convoy collaboration framework.

---

## Architecture & Swarm Mapping

The OpenAI Agents SDK models **conversational transitions (handoffs) and local orchestration**. Convoy models **project truth (event logs, KV storage, and schedules)**. They are complementary:

```
┌───────────────────────────────────────────────────────────────────┐
│                     Convoy Server (Event Log)                     │
└───────────────────────────────────────────────────────────────────┘
         ▲                             ▲                     ▲
         │ heartbeat & events          │ read/write KV       │ handoff POST
 ┌───────┴───────┐             ┌───────┴───────┐     ┌───────┴───────┐
 │ Leader Agent  │ ──handoff──►│  Dev Agent    │ ───►│   QA Agent    │
 │ (Hermes / A2A)│             │ (OpenClaw)    │     │(OpenAI Agents)│
 └───────────────┘             └───────────────┘     └───────────────┘
```

### Mapping Swarm to Convoy:
1. **Agent Definitions**: OpenAI `Agent` instances (e.g., `QA Agent`) are defined declaratively with system instructions and tools.
2. **Tool Invocation**: Agent tools are mapped directly to Convoy's SDK functions (`heartbeat`, `report`, `done`, `kv_set`, `kv_get`).
3. **Handoff Primitives**: Swarm handoffs (returning an `Agent` instance) map to Convoy's first-class `POST /api/tasks/{id}/handoff` mechanism, informing the board that ownership has shifted.

---

## Onboarding Protocol for QA Agent

When the QA Agent is assigned a task, it follows this automated pipeline:

1. **Join & Register**: Calls `/api/register` with capability `["qa", "openai-agents"]` and role `qa` (mints a bearer token).
2. **Read WIP & Context**:
   - Checks for pending handoffs via `GET /api/handoffs`.
   - Reads the task timeline via `GET /api/tasks/{task_id}` (utilizing the new S9.2 agent read access).
   - Reads execution context from the namespace `task:{task_id}` via `GET /api/kv/task:{task_id}` (e.g. `wip_context`).
3. **Accept Handoff**: Marks the handoff active using `POST /api/handoffs/{id}/accept`.
4. **Execute Review**: Runs code quality reviews, lint checks, or unit test verification.
5. **Log Token Usage**: Self-reports all input/output tokens to `POST /api/usage` for costing accuracy.
6. **Publish Artifact & Handoff**:
   - Publishes test reports/reviews using `artifact_published`.
   - Saves context in `task:{task_id}` KV store.
   - Hands work back to the developer or leader agent.

---

## Running the QA Pilot

The QA pilot agent is implemented in `agent/qa_agent_pilot.py`.

### Prerequisites
1. Set up your OpenAI API key:
   ```bash
   export OPENAI_API_KEY="your-api-key"
   ```
2. Ensure you have the `openai-agents` package installed:
   ```bash
   pip install openai-agents
   ```

### Execution
Run the pilot agent against a local or remote Convoy server:
```bash
# Point to local convoy server
export CONVOY_SERVER="http://localhost:8000"

# Run the QA agent pilot
python agent/qa_agent_pilot.py --task "s9-1"
```

The script will automatically:
- Register the `antigravity-qa` agent.
- Fetch the task board (proving S9.2 agent read access works).
- Run a simulated/real QA review using the OpenAI Agents SDK.
- Log token usage.
- Upload an artifact and hand off the task.
