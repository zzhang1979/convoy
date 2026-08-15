FROM python:3.12-slim

WORKDIR /app

# System deps (minimal — sqlite is stdlib)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App
COPY server/ server/
COPY ui/ ui/
COPY agent/ agent/

# Startup-wait entrypoint (S6.2): blocks until /api/health is live
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV CONVOY_DB=/data/convoy.db
ENV CONVOY_COMMANDER_TOKEN=convoy-cmd-2026
EXPOSE 8000

VOLUME ["/data"]

# Note: module imports use `server.models` so run as package from /app
# Entrypoint waits for readiness first (docker healthcheck polish / startup wait).
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
