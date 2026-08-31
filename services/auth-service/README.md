# auth-service

Authentication service for the Voice AI English tutor. Owns **identity** (email,
password, Google link) and issues **RS256 JWTs**. Profiles live in `user-service`.

Python + FastAPI, async SQLAlchemy 2.0, PostgreSQL, Alembic. Google OAuth2
(Authorization Code) done by hand with httpx; passwords hashed with bcrypt.

## Endpoints

| Method | Path                    | Purpose                                  |
|--------|-------------------------|------------------------------------------|
| POST   | `/auth/register`        | Local sign-up (email + password)         |
| POST   | `/auth/login`           | Local login → access + refresh tokens    |
| GET    | `/auth/google/login`    | Redirect to Google consent               |
| GET    | `/auth/google/callback` | Handle Google redirect → tokens          |
| POST   | `/auth/refresh`         | Exchange a refresh token for a new pair  |
| GET    | `/auth/me`              | Current identity (requires access token) |
| GET    | `/auth/public-key`      | RS256 public key (for other services)    |
| GET    | `/health`               | Liveness                                 |

## Ports (to avoid clashing with user-service)

- API: http://localhost:8001 (Swagger at `/docs` in dev; disabled when `ENV=prod`)
- Postgres: localhost:5433

## Run with Docker

```bash
# 1. Google credentials (optional for local/password flows, required for Google login)
cp .env.example .env   # fill GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET

# 2. up — waits for Postgres, generates RS256 keys, runs migrations, starts API
docker compose up --build
```

On first start the API container generates an RS256 key pair into the `auth_keys`
volume (`keys/private.pem`, `keys/public.pem`) and `alembic upgrade head` creates
`au_users`. The API does NOT create tables itself; migrations do.

## Google OAuth setup

In Google Cloud Console → APIs & Services → Credentials, create an **OAuth client ID**
(Web application) and add the redirect URI:

```
http://localhost:8001/auth/google/callback
```

Put the client id/secret in `.env`.

## JWT strategy

- **RS256**: the auth-service signs with `keys/private.pem`.
- Other services verify tokens with the **public** key (`keys/public.pem`) — no shared
  secret, no call back to auth-service. Distribute `public.pem` to those services.
- Access token ~15 min, refresh token ~7 days (configurable in `.env`).

## Checks (run before committing)

```bash
ruff format --check .
ruff check .
mypy .
pytest -m "not integration"
```

## Notes / next steps

- On registration/first Google login we currently only create the identity. Wiring a
  call to `user-service` to create the matching profile is a planned follow-up.
- Refresh tokens are currently stateless (not stored). Add an `au_refresh_tokens`
  table (or Redis) later if token revocation is needed.
