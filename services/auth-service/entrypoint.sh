#!/usr/bin/env sh
# Generate RS256 keys (if missing), apply DB migrations, then start the API.
set -e

echo "[entrypoint] ensuring RS256 keys..."
python -m app.utils.keygen

echo "[entrypoint] applying migrations..."
alembic upgrade head

echo "[entrypoint] starting API..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
