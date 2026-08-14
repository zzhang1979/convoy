#!/usr/bin/env bash
# Convoy agent helper — one-command onboarding + reporting.
# Usage:
#   ./convoy-agent.sh join <server> <agent_id> [name]
#   ./convoy-agent.sh report <server> <secret> <task_id> <type> [json_payload]
#   ./convoy-agent.sh heartbeat <server> <secret>
set -euo pipefail

SERVER="${CONVOY_SERVER:-http://192.168.0.154:8000}"

join() {
  local agent_id="$2" name="${3:-$2}"
  local resp
  resp=$(curl -sf -X POST "$SERVER/api/register" \
    -H "Content-Type: application/json" \
    -d "{\"agent_id\":\"$agent_id\",\"name\":\"$name\",\"capabilities\":[\"shell\",\"web\"]}")
  echo "$resp"
  echo
  echo "Save your secret — you'll need it for reporting."
}

report() {
  local secret="$2" task_id="$3" type="$4" payload="${5:-{}}"
  local event_id
  event_id=$(cat /proc/sys/kernel/random/uuid)
  curl -sf -X POST "$SERVER/api/events" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $secret" \
    -d "{\"event_id\":\"$event_id\",\"task_id\":\"$task_id\",\"type\":\"$type\",\"payload\":$payload}" \
    | python3 -m json.tool 2>/dev/null || echo "event sent"
}

heartbeat() {
  local secret="$2"
  local event_id
  event_id=$(cat /proc/sys/kernel/random/uuid)
  curl -sf -X POST "$SERVER/api/events" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $secret" \
    -d "{\"event_id\":\"$event_id\",\"type\":\"heartbeat\",\"payload\":{}}" \
    | python3 -m json.tool 2>/dev/null || echo "heartbeat sent"
}

case "${1:-}" in
  join)     join "$@" ;;
  report)   report "$@" ;;
  heartbeat) heartbeat "$@" ;;
  *) echo "Usage: $0 {join|report|heartbeat} ..." >&2; exit 1 ;;
esac
