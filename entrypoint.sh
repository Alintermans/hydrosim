#!/bin/sh
# Ensure the data volume is usable and the schema exists, then serve.
set -e

DATA_DIR="${DATA_DIR:-/data}"

if ! mkdir -p "$DATA_DIR" 2>/dev/null || [ ! -w "$DATA_DIR" ]; then
    echo "[entrypoint] FATAL: DATA_DIR=$DATA_DIR is not writable by uid $(id -u)." >&2
    echo "[entrypoint] Use a named Docker volume for this path (in Coolify: Persistent" >&2
    echo "[entrypoint] Storage -> Volume Mount, not a host bind mount)." >&2
    exit 1
fi

echo "[entrypoint] Data directory: $DATA_DIR"
echo "[entrypoint] Initialising database (idempotent)…"
flask --app app init-db

echo "[entrypoint] Starting gunicorn…"
exec gunicorn -c gunicorn.conf.py wsgi:app
