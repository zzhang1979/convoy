# Convoy — Antigravity Onboarding Pack

Welcome, new collaborator (**stonechueng@gmail.com**)! Convoy is designed as a lean, self-documenting project collaboration system built around an append-only event log.

This onboarding pack acts as a guide to help you quickly understand the project map, our event model, Python SDK usage, test recipes, and local deployment options.

---

## 📁 Repository Directory Map

The repository is structured as a single monorepo containing the backend server, the commander frontend dashboard, client-side agents/SDK, integration tests, and architecture documents:

```
convoy/
├── server/                      # Backend FastAPI Application
│   ├── main.py                  # API endpoints, routing, and HTTP authentication
│   ├── models.py                # Database connection, schemas, and direct CRUD operations
│   └── derive.py                # Read-model projection logic to derive board state
│
├── ui/                          # Frontend Dashboard
│   └── index.html               # Single glass-pane commander dashboard (Vanilla HTML/CSS/JS)
│
├── agent/                       # Agent Scripts & Clients
│   ├── convoy_sdk.py            # Python SDK to register & report events (Hermes/custom bots)
│   ├── convoy-agent.sh          # Lightweight bash-based curl script for agent reporting
│   └── qa_agent_pilot.py        # OpenAI Agents SDK pilot verification agent
│
├── tests/                       # Automated Test Suites
│   ├── conftest.py              # Pytest fixtures and isolated database setup
│   ├── test_integration.py      # Core agent flow and registration checks
│   └── test_sprint*.py          # Iterative sprint verification tests
│
└── docs/                        # Specifications, findings, and onboarding packs
```

---

## ⚡ The Event Model (Facts, Not States)

We store historical facts (events) in an append-only log, rather than maintaining a mutable state machine. This design eliminates state transition synchronization bugs.

### 1. Database Schema
Events are stored in SQLite/Postgres with client-supplied UUIDs for idempotency:

```sql
CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT NOT NULL UNIQUE,       -- client-supplied dedupe key
    agent_id    TEXT NOT NULL,
    task_id     TEXT,                       -- optional, groups events
    type        TEXT NOT NULL,              -- created|started|blocked_on|unblocked|done|heartbeat|...
    payload     TEXT NOT NULL DEFAULT '{}', -- JSON metadata (reason, URL, etc.)
    received_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 2. Status Derivation Logic
The status of a task is derived live on query from the sequence of facts:
- **`done`**: Has a `done` event or published artifact.
- **`review`**: Artifacts exist (`artifact_published` event).
- **`stuck`**: Latest event is `blocked_on` (without a subsequent `unblocked`).
- **`stale`**: The task is running (`doing`) but the assignee agent's heartbeat (or task heartbeat) is older than 5 minutes.
- **`doing`**: Any event after `created` (with recent heartbeat activity).
- **`todo`**: Only a `created` event exists.

---

## 🐍 Python SDK Quickstart & Usage

To integrate custom agents or bots with Convoy, use the Python client in `agent/convoy_sdk.py`.

### 1. Register / Re-join
An agent registers automatically on first instantiation. Re-instantiating with the same `agent_id` is idempotent and reuses the generated secret token.

```python
from agent.convoy_sdk import ConvoyAgent

agent = ConvoyAgent(
    server="http://localhost:8000",
    agent_id="my-agent-id",
    role="engineer",
    capabilities=["shell", "code-review"],
    name="My Dev Bot"
)
```

### 2. Reporting Progress
Agents append events to report task statuses:

```python
# Report progress
agent.report(task_id="T-101", note="Refactoring auth routines", pct=50)

# Self-report LLM token usage (for costing dashboard)
agent.report_usage(tokens_in=12500, tokens_out=850, model="gpt-4o-mini", task_id="T-101")

# Mark done and publish code artifacts
agent.done(task_id="T-101", summary="Merged auth changes", artifacts=["https://github.com/.../commit/abc"])
```

### 3. Sharing Task Context (KV Store)
Agents read and write context in namespaces matching `task:<task_id>`:

```python
# Set work context for the next developer
agent.kv_set("task:T-101", "wip_context", {
    "blockers": ["missing token"],
    "next_steps": ["add migrations", "run tests"]
})
```

---

## 🧪 Testing Recipes

The codebase is tested using `pytest`. Because we run within a sandboxed environment during development, follow these execution practices:

### 1. Running Tests Locally
Always set the `PYTHONPATH` variable to enable importing the parent `server` module:

```bash
PYTHONPATH=. .venv/bin/pytest tests/
```

### 2. Sandbox Troubleshooting
Under the standard IDE sandbox, commands are isolated from files outside the repository.
- **`Fatal Python error: init_fs_encoding`**: This occurs if Python tries to reach runtime codecs outside the workspace.
- **Solution**: Execute the test runner with sandbox bypassed (`BypassSandbox: true` inside IDE tools) to allow network and host filesystem access.

---

## 🚀 Deployment Recipes

### 1. Run Server via Uvicorn (Development)
Spin up the FastAPI backend locally:

```bash
# Set the commander authorization token
export CONVOY_COMMANDER_TOKEN="convoy-cmd-2026"

# Run Uvicorn dev server
.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
```
- Open `http://localhost:8000/` in the browser.
- Open `http://localhost:8000/api/health` to confirm the SQLite database initialized cleanly.

### 2. Run via Docker Compose (Production-ready)
To deploy the backend, database volume, and automated health checks in containers:

```bash
docker compose up --build
```
- Maps the server to `http://localhost:8000`.
- Health checks automatically poll `/api/health`.
- Standardized environment variables for db setup and tokens are loaded from `docker-compose.yml`.
