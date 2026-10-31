#!/bin/bash
set -e

echo "Running database migrations..."
cd /app/backend && alembic upgrade head

# The public demo (FINANCE_DEMO_MODE=true) runs on its own database holding only the Claudius
# seed; every start rebuilds it so its dates are current (a nightly restart keeps them so).
if [ "${FINANCE_DEMO_MODE:-false}" = "true" ]; then
    echo "Demo mode: rebuilding the Claudius Banks data..."
    cd /app && python scripts/seed_test_data.py --reset
fi

echo "Starting Tallied..."
exec gunicorn app.main:app \
    -k uvicorn.workers.UvicornWorker \
    -w 2 \
    -b 0.0.0.0:8000 \
    --access-logfile - \
    --error-logfile - \
    --chdir /app/backend
