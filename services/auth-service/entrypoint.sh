#!/usr/bin/env sh
# Apply DB migrations, then start the API. Fail fast if migrations fail.
# JWT keys are provided via env (JWT_PRIVATE_KEY); see .env.example to generate a pair.
set -e

echo "[entrypoint] applying migrations..."
alembic upgrade head

echo "[entrypoint] starting API..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
