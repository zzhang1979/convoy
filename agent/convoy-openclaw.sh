#!/usr/bin/env bash
# Convoy OpenClaw adapter — one-command onboarding for OpenClaw agents.
# OpenClaw agents speak HTTP; this wraps Convoy's REST API in simple commands.
#
# Usage:
#   ./convoy-openclaw.sh join <server> <agent_id> [name]     # register, save secret
#   ./convoy-openclaw.sh heartbeat                           # keep-alive
#   ./convoy-openclaw.sh report <task_id> <note>             # progress update
#   ./convoy-openclaw.sh done <task_id> <summary> [artifact_url]
#   ./convoy-openclaw.sh blocked <task_id> <reason>
#   ./convoy-openclaw.sh kv set <namespace> <key> <json_value>
#   ./convoy-openclaw.sh kv get <namespace> <key>
#   ./convoy-openclaw.sh kv list <namespace> [prefix]
#   ./convoy-openclaw.sh handoff <task_id> <to_agent> <notes>
#   ./convoy-openclaw.sh sop                                  # show collaboration rules
#
# State: secret saved to ~/.convoy_secret (chmod 600)
set -euo pipefail

SERVER="${CONVOY_SERVER:-http://192.168.0.154:8000}"
SECRET_FILE="${CONVOY_SECRET_FILE:-$HOME/.convoy_secret}"

secret() {
  if [ ! -f "$SECRET_FILE" ]; then
    echo "No secret found — run: $0 join <server> <agent_id>" >&2
    exit 1
  fi
  cat "$SECRET_FILE"
}

cmd_join() {
  local agent_id="$2" name="${3:-$2}"
  local resp
  resp=$(curl -sf -X POST "$SERVER/api/register" \
    -H "Content-Type: application/json" \
    -d "{\"agent_id\":\"$agent_id\",\"name\":\"$name\",\"capabilities\":[\"shell\",\"web\",\"openclaw\"]}")
  local sec
  sec=$(echo "$resp" | python3 -c "import json,sys; print(json.load(sys.stdin)['secret'])")
  echo "$sec" > "$SECRET_FILE"
  chmod 600 "$SECRET_FILE"
  echo "✅ Joined as $agent_id — secret saved to $SECRET_FILE"
  echo "📋 SOP:"
  echo "$resp" | python3 -c "
import json,sys
d = json.load(sys.stdin)
for r in d.get('sop', []):
    print(f\"  {r['priority']}. {r['title']}: {r['body']}\")
if d.get('wip_handoffs'):
    print('📥 WIP handoffs waiting for you:')
    for h in d['wip_handoffs']:
        print(f\"  - task {h['task_id']} from {h['from_agent']}: {h['notes']}\")
"
}

cmd_event() {
  local type_="$1" task_id="$2" payload="${3:-{}}"
  local event_id
  event_id=$(cat /proc/sys/kernel/random/uuid)
  curl -sf -X POST "$SERVER/api/events" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $(secret)" \
    -d "{\"event_id\":\"$event_id\",\"task_id\":\"$task_id\",\"type\":\"$type_\",\"payload\":$payload}" \
    | python3 -m json.tool 2>/dev/null || echo "event sent"
}

cmd_heartbeat() {
  local event_id
  event_id=$(cat /proc/sys/kernel/random/uuid)
  curl -sf -X POST "$SERVER/api/events" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $(secret)" \
    -d "{\"event_id\":\"$event_id\",\"type\":\"heartbeat\",\"payload\":{}}" >/dev/null
  echo "❤️  heartbeat sent"
}

cmd_report() {
  cmd_event "progress" "$2" "{\"note\":\"$3\"}"
}

cmd_done() {
  local task_id="$2" summary="$3" url="${4:-}"
  if [ -n "$url" ]; then
    cmd_event "artifact_published" "$task_id" "{\"url\":\"$url\",\"kind\":\"artifact\"}" >/dev/null
  fi
  cmd_event "done" "$task_id" "{\"summary\":\"$summary\"}"
}

cmd_blocked() {
  cmd_event "blocked_on" "$2" "{\"reason\":\"$3\"}"
}

cmd_kv() {
  local op="$2" namespace="$3" key="$4" value="${5:-}"
  case "$op" in
    set)
      curl -sf -X PUT "$SERVER/api/kv/$namespace/$key" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $(secret)" \
        -d "{\"key\":\"$key\",\"value\":$value}" ;;
    get)
      curl -sf "$SERVER/api/kv/$namespace/$key" \
        -H "Authorization: Bearer $(secret)" ;;
    list)
      curl -sf "$SERVER/api/kv/$namespace?prefix=$value" \
        -H "Authorization: Bearer $(secret)" ;;
  esac
  echo
}

cmd_handoff() {
  local task_id="$2" to_agent="$3" notes="${4:-}"
  curl -sf -X POST "$SERVER/api/tasks/$task_id/handoff" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $(secret)" \
    -d "{\"to_agent\":\"$to_agent\",\"notes\":\"$notes\"}"
  echo
}

cmd_sop() {
  curl -sf "$SERVER/api/sop" -H "Authorization: Bearer $(secret)" \
    | python3 -c "
import json,sys
for r in json.load(sys.stdin)['sop']:
    print(f\"{r['priority']}. {r['title']}: {r['body']}\")
"
}

cmd_usage() {
  # usage <tokens_in> <tokens_out> [model] [task_id]
  local tin="$2" tout="$3" model="${4:-unknown}" task="${5:-}"
  local body="{\"tokens_in\":$tin,\"tokens_out\":$tout,\"model\":\"$model\""
  [ -n "$task" ] && body="$body,\"task_id\":\"$task\""
  body="$body}"
  curl -sf -X POST "$SERVER/api/usage" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $(secret)" \
    -d "$body"
  echo
}

case "${1:-}" in
  join)      cmd_join "$@" ;;
  heartbeat) cmd_heartbeat ;;
  report)    cmd_report "$@" ;;
  done)      cmd_done "$@" ;;
  blocked)   cmd_blocked "$@" ;;
  kv)        cmd_kv "$@" ;;
  handoff)   cmd_handoff "$@" ;;
  sop)       cmd_sop ;;
  usage)     cmd_usage "$@" ;;
  *) echo "Usage: $0 {join|heartbeat|report|done|blocked|kv|handoff|sop|usage} ..." >&2; exit 1 ;;
esac
