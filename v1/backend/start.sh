#!/usr/bin/env bash
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Seeding catalog (line items, metrics, signals, periods)..."
python -m app.seed.seed_catalog

echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
