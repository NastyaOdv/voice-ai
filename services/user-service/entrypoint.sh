#!/usr/bin/env sh
# Apply DB migrations, then start the API. Fail fast if migrations fail.
set -e

echo "[entrypoint] applying migrations..."
alembic upgrade head

echo "[entrypoint] starting API..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
