#!/bin/sh
# Entrypoint: run migrations then start the server.
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting Wavy Labs license server..."
exec uvicorn main:app \
    --host "${APP_HOST:-0.0.0.0}" \
    --port "${APP_PORT:-8000}" \
    --workers 2 \
    --proxy-headers \
    --forwarded-allow-ips "*"
