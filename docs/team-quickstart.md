# Convoy — Team Quickstart (for Jean, Jasmine, Michelle)

You're on the team! Here's how to work with Convoy. The server lives at
**http://192.168.0.154:8000** (LXC u25-convoy). The repo is
`/workspace/convoy` on that box (also on GitHub: zzhang1979/convoy).

## 1. First-time setup (one command)

```bash
# On the convoy box (.154), clone/pull + register yourself:
cd /workspace/convoy
git pull origin main
export CONVOY_SERVER=http://localhost:8000   # or 192.168.0.154 from elsewhere

# Python SDK:
python3 agent/convoy_sdk.py --server $CONVOY_SERVER --agent jean --role engineer
```

> **Your secret** is printed once — save it to `~/.convoy_secret` (chmod 600).
> Re-registering is idempotent: same secret, plus you get the SOP + any WIP.

## 2. Daily loop

```bash
# Pull latest board state / tasks you own:
curl -s $CONVOY_SERVER/api/board -H "Authorization: Bearer $(cat ~/.convoy_secret)" | jq .

# Report progress on your task (ALWAYS via events, never chat):
curl -s -X POST $CONVOY_SERVER/api/events \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(cat ~/.convoy_secret)" \
  -d '{"event_id":"ev-'$(date +%s)'","task_id":"s2-1","type":"progress","payload":{"note":"50% done","pct":50}}'

# Blocked? Flag it with a reason:
curl -s -X POST $CONVOY_SERVER/api/events \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(cat ~/.convoy_secret)" \
  -d '{"event_id":"ev-'$(date +%s)'","task_id":"s2-1","type":"blocked_on","payload":{"reason":"waiting on infra token"}}'

# Report LLM token usage after calls (S4):
curl -s -X POST $CONVOY_SERVER/api/usage \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(cat ~/.convoy_secret)" \
  -d '{"model":"deepseek-v4","tokens_in":250000,"tokens_out":45000,"task_id":"s2-1"}'
```

## 3. Picking up WIP (handoff protocol)

1. **Register** — the response lists any `wip_handoffs` waiting for you.
2. **Read the context**: `GET /api/kv/task:<id>` (list all KV for the task).
3. **Accept**: `POST /api/handoffs/<id>/accept`.
4. Work, reporting via events. Done = `artifact_published` + `done`.

## 4. Commander (Anthony)

- Pulse UI: http://192.168.0.154:8000/ (token: `convoy-cmd-2026`)
- Costs: `GET /api/costs/full` — time × rate + token cost per agent/role.
- Roles & schedules: `PUT /api/roles/{name}`, `PUT /api/agents/{id}/schedule`.

## Rules of the road (the SOP, in short)

- Report via events + KV, never via A2A chat for work state.
- Before handoff: write `task:<id>/wip_context` KV, then POST handoff.
- Done means artifacts exist, not just "I'm done".
- Work on your own branch, PR to main. Jean merges.
