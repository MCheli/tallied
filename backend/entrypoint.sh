#!/bin/bash
set -e

echo "Running database migrations..."
cd /app/backend && alembic upgrade head

echo "Starting Tallied..."
exec gunicorn app.main:app \
    -k uvicorn.workers.UvicornWorker \
    -w 2 \
    -b 0.0.0.0:8000 \
    --access-logfile - \
    --error-logfile - \
    --chdir /app/backend
