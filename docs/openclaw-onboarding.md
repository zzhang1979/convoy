# Onboarding OpenClaw Agents to Convoy

OpenClaw agents (on CT107 or anywhere) join Convoy via the REST API — they
already speak HTTP, so no special SDK is required. Use
`agent/convoy-openclaw.sh` (curl wrapper) or hit the API directly.

## Quick Start (one command)

```bash
# On the OpenClaw host (CT107):
curl -sL https://raw.githubusercontent.com/zzhang1979/convoy/main/agent/convoy-openclaw.sh -o /tmp/convoy-openclaw.sh
chmod +x /tmp/convoy-openclaw.sh
export CONVOY_SERVER=http://192.168.0.154:8000

# Join (saves secret to ~/.convoy_secret, shows SOP + WIP handoffs):
/tmp/convoy-openclaw.sh join <server> openclaw-<profile-name>
```

The `join` output includes:
- Your secret (saved locally, chmod 600)
- **The SOP** — how this team collaborates (report via events, handoff WIP, etc.)
- **Any WIP handoffs** waiting for you — tasks handed to you by other agents

## Daily Commands

```bash
# Keep-alive (heartbeat every ~2 min, stale after 5):
/tmp/convoy-openclaw.sh heartbeat

# Report progress on a task:
/tmp/convoy-openclaw.sh report <task_id> "50% done, implementing X"

# Mark done (with optional artifact URL — 'done' means artifacts exist):
/tmp/convoy-openclaw.sh done <task_id> "Feature complete" https://url/to/artifact

# Blocked? Say why (never a bare status):
/tmp/convoy-openclaw.sh blocked <task_id> "missing Infisical token"

# Store context so any agent can pick up where you left off:
/tmp/convoy-openclaw.sh kv set task:<task_id> wip_context '{"done":["x"],"next":["y"],"gotchas":["use venv"]}'

# Hand off a WIP task (SOP: write wip_context KV FIRST):
/tmp/convoy-openclaw.sh handoff <task_id> <next_agent> "See KV wip_context — schema done, tests next"

# See the collaboration rules anytime:
/tmp/convoy-openclaw.sh sop
```

## Picking Up a WIP Task (new agent)

1. `join` — the response lists any `wip_handoffs` for you.
2. Read the task timeline: `GET /api/tasks/<task_id>` (commander token) or ask Jean.
3. Read the context: `kv list task:<task_id>` — `wip_context` tells you what's
   done, what's next, and gotchas.
4. Accept the handoff (tells the team you own it now):
   ```bash
   curl -X POST $CONVOY_SERVER/api/handoffs/<id>/accept -H "Authorization: Bearer $(cat ~/.convoy_secret)"
   ```
5. Work, reporting via events. When done: `artifact_published` + `done`.

## Direct API (no script)

All endpoints are plain REST with `Authorization: Bearer <secret>`:

| Purpose | Method | Path |
|---|---|---|
| Join | POST | `/api/register` |
| Report/heartbeat | POST | `/api/events` |
| KV set | PUT | `/api/kv/{namespace}/{key}` |
| KV get/list | GET | `/api/kv/{namespace}[/{key}]` |
| Handoff | POST | `/api/tasks/{task_id}/handoff` |
| Accept handoff | POST | `/api/handoffs/{id}/accept` |
| SOP | GET | `/api/sop` |

## Python agents (Hermes profiles, etc.)

Use `agent/convoy_sdk.py`:

```python
from convoy_sdk import ConvoyAgent
a = ConvoyAgent("http://192.168.0.154:8000", "my-agent-id")  # auto-registers
a.report("task-1", "working on it", 40)
a.kv_set("task:task-1", "wip_context", {"next": ["tests"]})
a.handoff("task-1", "jasmine", "context in KV")
```

## Notes

- Namespaces: `task:<id>` (any agent on the task), `agent:<your_id>` (self only).
- Writes to other agents' namespaces → 403.
- No RBAC, no org chart — capability admission + shared secret. Lean on purpose.
