# Voice AI — English Tutor (project rules)

> Instructions for Claude when working in the `web-eng` repository.
> **Chat language with the user: Russian. Everything inside the project: English.**

## What this project is

A web app for **spoken English practice** with a voice AI agent.
The user speaks → the agent replies **with voice** and, in parallel, leaves
**text notes about the user's grammar mistakes**.

Based on the "Voice AI Assistant" task (an STT → LLM → TTS orchestrator):
https://git.sysgears.com/scala-team/ai-framework-2026/-/issues/1

## Locked decisions (scope)

- **Level 1** — asynchronous "walkie-talkie" mode. The user records a full voice
  message, sends it to the backend, gets back a ready audio reply + notes.
  No real-time streaming / VAD / barge-in at this stage.
- **Corrections: grammar only.** No pronunciation, no vocabulary.
  (Pronunciation can't be caught via STT anyway — Whisper normalizes the text.)
- **Architecture: microservices.** This is a deliberate learning goal — the user
  has not worked with microservices before. The split must be meaningful, not for show.
- **Pet project, resume-oriented.** Weigh resume value when choosing tech, but do
  not pull everything in at once — balance "it works" vs "don't drown".

## Core mechanic (do not break)

Pipeline: `Audio (User) → STT → LLM → TTS → Audio + text notes`

The LLM step returns a **structured response** (structured output / JSON), two parts:
- `spoken_reply` — a natural line to continue the conversation → **goes to TTS**;
- `corrections[]` — list of grammar mistakes (`you_said`, `better`, `note`)
  → **text only in the UI**, never sent to TTS.

The agent keeps a natural spoken conversation; mistakes accumulate as on-screen notes.

Other mandatory pipeline rules:
- **LLM is stateless.** The orchestrator itself keeps session history and sends the
  full context (System → User → Assistant → User …) on every user turn.
- **STT in verbatim mode** (no normalization), otherwise mistakes are lost.
- **LLM vendor behind an interface** (trait/class/adapter) to avoid vendor lock-in.

## Coding conventions

- **English only** for all code, identifiers, comments, docs, and commit messages.
- **Functions use `snake_case`** (e.g. `parse_audio`). Do NOT prefix a function name
  with a leading underscore (no `_parse_audio`).
- Python: type hints everywhere, `async` for I/O, follow FastAPI idioms.

### Service layout (every service follows this)

```
app/
  routes/         # FastAPI routers — thin: parse request, call a service, return a schema
  services/       # business logic (orchestrates repositories + utils); raises domain errors
  repositories/   # data access — all SQLAlchemy queries live here (one per aggregate)
  models/         # SQLAlchemy ORM models
  schemas/        # Pydantic request/response models
  utils/          # cross-cutting helpers (jwt, passwords, dependencies, exceptions, …)
  conf/           # config.py — DBSettings (env_prefix DB_) + app Settings
  db/             # async_session_manager.py — Base, DatabaseSessionManager, get_db_async_session
  logger/         # logger_config.py — configured `logger`
  main.py
```

Dependency direction: `routes → services → repositories → models`. Keep routers thin;
never put SQL in routes, never import FastAPI in repositories.

**Repositories** are plain module-level `async` functions (NOT classes). Files end
with `_repo.py` (e.g. `user_repo.py`). Every function takes the session as its first
arg `db: AsyncSession`. Read functions just query; mutating functions follow this shape:

```python
async def create_user(db: AsyncSession, user: User) -> User:
    try:
        db.add(user)
        await db.flush()
        await db.refresh(user)
        await db.commit()
        return user
    except SQLAlchemyError as e:
        await db.rollback()
        raise e
```

Services hold the `db` session and call these functions (`user_repo.create_user(self.db, …)`).

### Config & app wiring

- **Settings are lazy**: `conf/config.py` exposes `get_settings()`, `get_db_settings()`,
  `get_system_settings()` (each `@lru_cache`d) — call them where needed, never a
  module-level `settings = Settings()`.
- `app/app.py` exposes `get_application() -> FastAPI`: sets the Windows event-loop policy,
  toggles docs by `SystemSettings.env` (`prod` → docs off; else default Swagger at `/docs`),
  uses `ORJSONResponse`, adds middlewares, includes routers, defines `/health`. Where a
  service makes outbound HTTP (auth-service → Google OAuth), a shared `httpx.AsyncClient`
  is created in the `app_lifespan` on `app.state.http_client` (services without outbound
  HTTP don't create one). Root `main.py` is just `app = get_application()`. Uvicorn runs
  **`main:app`**.
- Global `catch_value_errors` middleware maps `ValueError`→422, `ResponseValidationError`→422,
  anything else→500 (logged). Lives in `utils/middleware.py`.
- **user-service auth is a middleware** (`jwt_auth`): validates a forwarded access token and
  puts `request.state.user_id`; routes read it via `get_current_user_id`. (auth-service keeps a
  DB-backed `get_current_user` dependency, since its `/me` loads the full `au_users` row.)

**DB access:** Postgres via **psycopg3** async (`postgresql+psycopg`). Connection
settings come from `DBSettings` (env vars `DB_USERNAME/PASSWORD/DATABASE/HOST/PORT/SSLMODE`).
`db/async_session_manager.py` exposes `Base`, the `sessionmanager`, and the
`get_db_async_session` FastAPI dependency. `sslmode=disable` locally; `require` for cloud PG.

### SQLAlchemy / Postgres models

Use the **classic `Column(...)` declarative style** — NOT the 2.0
`Mapped[...]` / `mapped_column` typed style. Foreign keys via `ForeignKey(Other.id)`
(only within the same service; cross-service references are plain columns, no FK).

**Table naming:** each service prefixes its tables with a short code — **user-service
→ `us_`** (`us_users`), **auth-service → `au_`** (`au_users`). Names are `snake_case`,
plural. Indexes follow the table name (e.g. `ix_us_users_email`).

### auth-service (decided)

- **Google OAuth2 (Authorization Code) + local email/password.** Own DB (`au_users`);
  profiles stay in user-service (link by `user_id`, no cross-service FK).
- **JWT signed with RS256.** auth-service holds the private key (`JWT_PRIVATE_KEY` env);
  other services verify with the public key (`JWT_PUBLIC_KEY` env), distributed
  out-of-band — no shared secret, no callback to auth. Access + refresh tokens.
- Ports: API `8001`, Postgres `5433` (user-service uses `8000` / `5432`).

### Service-to-service

- All services share an external Docker network **`webeng`** — create once with
  `docker network create webeng`. Unique service names: `auth-api`/`auth-db`,
  `user-api`/`user-db`. Root `docker-compose.yml` brings everything up via `include`.
- **JWT validation:** user-service (and future services) verify forwarded access
  tokens with auth's **public key**, provided out-of-band via env (`JWT_PUBLIC_KEY`, the
  RS256 public key PEM); auth signs with `JWT_PRIVATE_KEY`. No shared secret, no runtime
  key fetch, no per-request callback to auth. Generate a pair once with openssl (see
  auth-service `.env.example`). Client forwards the access token; each service checks it
  independently.
- Security posture: rely on network isolation (internal services not public) + JWT
  propagation. mTLS / service mesh are noted as future work, intentionally not built.

```python
class Call(Base):
    __tablename__ = "calls"

    id = Column(Integer, primary_key=True)
    total_score = Column(Numeric, nullable=False)
    client_id = Column(Integer, ForeignKey(Client.id), nullable=False)
    date = Column(DateTime, nullable=False)
    summary = Column(String, nullable=False)
    transcript = Column(String, nullable=False)
```

## Stack

- **Orchestrator: Python + FastAPI** (locked).

- **Service comms: RabbitMQ** (aio-pika), synchronous **RPC / request-reply** pattern.
- **Session cache: Redis** (hot LLM context); **Postgres** = source of truth.
- **Audio: local disk** for now (`STORAGE_DIR`, a mounted volume) — MinIO/S3 later.
- **orchestrator-service** owns the pipeline (tables `or_`), talks to STT/LLM/TTS
  workers over queues `stt.rpc` / `llm.rpc` / `tts.rpc`. Ports: API `8002`, PG `5434`,
  Redis `6379`, RabbitMQ `5672` (UI `15672`).

- **STT: faster-whisper** (locked) — `stt-service`, a `stt.rpc` queue worker (not HTTP).
  Model size via env (`base`, CPU/int8 default). Verbatim transcription.

- **LLM: Anthropic Claude** (locked) — `llm-service`, an `llm.rpc` worker. Official SDK
  (`AsyncAnthropic`), structured output via `messages.parse` + Pydantic (`spoken_reply` +
  `corrections`). Model via `LLM_MODEL` (default `claude-opus-5`); thinking disabled.
  **Realtime (E4)** splits this into two calls selected by a `mode` field: `stream_reply`
  streams the conversational line as plain-text deltas via `messages.stream` (worker
  publishes many `{delta}` then `{done,text}` over the `call_stream` protocol), and
  `corrections` is a separate structured `messages.parse` pass (`Corrections` model). The
  orchestrator segments the reply stream into sentences and voices each one as it lands.

- **Frontend: Angular 20 + Angular Material** (locked) — lives in `frontend/`.
  Standalone components, signals, lazy-loaded routes. **Cookie-based auth**: the SPA
  stores no tokens (they are httponly); it sends every request with `withCredentials`
  (a `credentialsInterceptor`) and resolves the current user via `GET /auth/me`.
  All API calls are namespaced under **`/api`** and a dev proxy (`proxy.conf.json`)
  rewrites `^/api` away, routing `/api/auth → :8001` and `/api/sessions → :8002` — this
  keeps cookies first-party (no CORS in dev) and avoids the SPA route `/sessions`
  colliding with the API path. Pages so far: `/login`, `/signup`, `/sessions`
  (guarded by `authGuard`). CORS on the services is still needed for a non-proxied
  (production) deploy.

- **TTS: Piper** (locked) — `tts-service`, a `tts.rpc` worker. Voice
  `en_US-lessac-medium` baked into the image (offline, CPU-first). Streams raw PCM and
  wraps it as WAV; contract `{text} → {audio_b64}` (base64 WAV). Chosen over XTTS v2 /
  Silero for CPU speed — comfortably inside the orchestrator's 8s best-effort timeout.

Still TBD — do NOT lock without the user's decision:
- Object storage for audio: MinIO · S3 (later)
- DevOps: docker-compose (baseline) · OpenTelemetry+Grafana · Kubernetes

> The repo has a `.venv` — Python confirmed.

## Development workflow (follow it)

Full details in `.claude/WORKFLOW.md`. Standard feature flow:

`/write-spec → /write-plan → /review-spec → /work`

- Before writing code: read/create the spec, read relevant `skills/`, make a plan.
- Write code test-first (see `skills/test-driven-development/SKILL.md`).
- **Git is the user's job.** Do NOT run `git commit` / `git push`, open PRs, or set
  up git hooks. Before the user commits, they run the checks manually
  (`ruff`, `mypy`, `pytest`).

## How I (Claude) should work here

- Before writing code for an undecided stack question — ask / propose options,
  don't choose silently.
- Don't over-engineer: Level 1 needs only 4 services (orchestrator + STT + LLM + TTS)
  plus storage. No Kafka/K8s without an explicit request.
- Offer choices as options with trade-offs; put the recommendation first.
- Keep this file up to date: as decisions land, update "Stack" / "Locked decisions".
