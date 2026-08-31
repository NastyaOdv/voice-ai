# user-service

User service for the Voice AI English tutor. Python + FastAPI, async SQLAlchemy 2.0,
PostgreSQL, Alembic migrations.

## Layout

```
app/
  routes/        # FastAPI routers (thin)
  services/      # business logic
  repositories/  # data access (SQLAlchemy queries)
  models/        # SQLAlchemy models (User)
  schemas/       # Pydantic schemas
  utils/         # jwt, dependencies, ...
  conf/          # DBSettings (DB_ prefix) + app Settings
  db/            # async_session_manager.py (Base, DatabaseSessionManager, get_db_async_session)
  logger/        # logger_config.py
  app.py         # get_application() factory (middlewares + routers)
main.py           # entrypoint: event-loop policy + app = get_application()
migrations/       # Alembic (env.py, versions/)
```

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   POSIX: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Run everything with Docker (recommended)

Services share the external `webeng` network — create it once:

```bash
docker network create webeng      # one-time
docker compose up --build
```

To bring up user-service **and** auth-service together, use the root compose:
`docker compose up --build` from the repo root.

This starts Postgres, waits until it is healthy, then the `api` container runs
`alembic upgrade head` (via `entrypoint.sh`) — which creates the tables — and starts
uvicorn on http://localhost:8000. The API does NOT create tables itself; migrations do.

Health check: http://localhost:8000/health

`GET /me` is a protected example — send `Authorization: Bearer <access_token>` from
auth-service; user-service validates it with auth's public key (fetched from
`AUTH_PUBLIC_KEY_URL`) and returns the token's user id.

## Run locally without Docker

```bash
docker compose up -d db          # just Postgres on :5432
alembic upgrade head             # apply migrations (creates the tables)
uvicorn main:app --reload        # start the API
```

Rollback the last migration: `alembic downgrade -1`.

## Checks (run before committing)

```bash
ruff format --check .
ruff check .
mypy .
pytest -m "not integration"
```

## Schema — `us_users`

| Column        | Type         | Notes                    |
|---------------|--------------|--------------------------|
| id            | UUID         | primary key              |
| first_name    | varchar(100) | required                 |
| last_name     | varchar(100) | required                 |
| email         | varchar(255) | required, unique         |
| phone_number  | varchar(32)  | optional                 |
| created_at    | timestamptz  | default now()            |
| updated_at    | timestamptz  | default now(), on update |
