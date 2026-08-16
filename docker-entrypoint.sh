#!/bin/sh
# Convoy startup-wait entrypoint (S6.2 docker healthcheck polish).
#
# Fix deadlock: we run uvicorn in the background first, then block/wait
# until /api/health is live before completing the entrypoint step by
# waiting on the uvicorn process PID in the foreground.
set -eu

URL="${CONVOY_HEALTH_URL:-http://localhost:8000/api/health}"
TIMEOUT="${CONVOY_STARTUP_TIMEOUT:-60}"
INTERVAL="${CONVOY_STARTUP_INTERVAL:-1}"

# Start the uvicorn server in the background
echo "[convoy] starting server in background: $@"
"$@" &
PID=$!

echo "[convoy] waiting for $URL to become healthy (timeout=${TIMEOUT}s) ..."

# Set up signal trapping to clean up the background process if container stops
cleanup() {
    echo "[convoy] shutting down background server (PID=$PID)..."
    kill -TERM "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
}
trap cleanup TERM INT

elapsed=0
healthy=0
while [ "$elapsed" -lt "$TIMEOUT" ]; do
    # Check if background process has died
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "[convoy] ERROR: server process died early" >&2
        wait "$PID" || true
        exit 1
    fi

    if curl -fsS "$URL" >/dev/null 2>&1; then
        echo "[convoy] ready in ${elapsed}s — server is healthy"
        healthy=1
        break
    fi
    sleep "$INTERVAL"
    elapsed=$((elapsed + INTERVAL))
done

if [ "$healthy" -eq 1 ]; then
    # Bring background process to foreground
    wait "$PID"
else
    echo "[convoy] ERROR: app did not become healthy within ${TIMEOUT}s" >&2
    kill -TERM "$PID" 2>/dev/null || true
    exit 1
fi

