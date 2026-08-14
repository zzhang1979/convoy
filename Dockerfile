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

ENV CONVOY_DB=/data/convoy.db
ENV CONVOY_COMMANDER_TOKEN=convoy-cmd-2026
EXPOSE 8000

VOLUME ["/data"]

# Note: module imports use `server.models` so run as package from /app
CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
