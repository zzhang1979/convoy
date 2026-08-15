#!/bin/sh
# Convoy startup-wait entrypoint (S6.2 docker healthcheck polish).
#
# `docker compose up` marks the container ready only after the app is actually
# serving /api/health (the same readiness probe the repo's own wait_health()
# and the compose healthcheck use). This is the "startup wait": uvicorn +
# lifespan init_db/seed must finish before we declare the node up, so a slow
# first boot never flaps the healthcheck or races into failure.
#
# Compose healthcheck runs in parallel; start_period in docker-compose.yml
# gives this wait a grace window before retries count against the container.
set -eu

URL="${CONVOY_HEALTH_URL:-http://localhost:8000/api/health}"
TIMEOUT="${CONVOY_STARTUP_TIMEOUT:-60}"
INTERVAL="${CONVOY_STARTUP_INTERVAL:-1}"

echo "[convoy] waiting for $URL (timeout=${TIMEOUT}s) ..."

elapsed=0
while [ "$elapsed" -lt "$TIMEOUT" ]; do
    if curl -fsS "$URL" >/dev/null 2>&1; then
        echo "[convoy] ready in ${elapsed}s — starting server"
        exec "$@"
    fi
    sleep "$INTERVAL"
    elapsed=$((elapsed + INTERVAL))
done

echo "[convoy] ERROR: app did not become healthy within ${TIMEOUT}s" >&2
exit 1
