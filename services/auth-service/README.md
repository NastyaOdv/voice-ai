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
| GET    | `/health`               | Liveness                                 |

## Ports (to avoid clashing with user-service)

- API: http://localhost:8001 (Swagger at `/docs` in dev; disabled when `ENV=prod`)
- Postgres: localhost:5433

## Run with Docker

```bash
# 1. Generate an RS256 key pair once and paste it into the .env files
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out private.pem
openssl rsa -in private.pem -pubout -out public.pem
#   -> private.pem as JWT_PRIVATE_KEY into auth-service/.env (or the root .env)
#   -> public.pem  as JWT_PUBLIC_KEY  into user-service/.env and orchestrator-service/.env

# 2. Google credentials (optional for local/password flows, required for Google login)
cp .env.example .env   # fill GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / JWT_PRIVATE_KEY

# 3. up — waits for Postgres, runs migrations, starts API
docker compose up --build
```

The RS256 keys come from env (`JWT_PRIVATE_KEY`), not from disk. `alembic upgrade head`
creates `au_users` on start; the API does NOT create tables itself, migrations do.

## Google OAuth setup

In Google Cloud Console → APIs & Services → Credentials, create an **OAuth client ID**
(Web application) and add the redirect URI:

```
http://localhost:8001/auth/google/callback
```

Put the client id/secret in `.env`.

## JWT strategy

- **RS256**: the auth-service signs with the private key from `JWT_PRIVATE_KEY` (env).
- Other services verify tokens with the **public** key from `JWT_PUBLIC_KEY` (env) — no
  shared secret, no call back to auth-service. Generate a pair with openssl (see above)
  and distribute `JWT_PUBLIC_KEY` to those services.
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
