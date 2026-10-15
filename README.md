# Voice AI — English Tutor

A web app for **spoken English practice** with a voice AI agent. You talk, the tutor
answers **with its voice** and keeps the conversation going, and in parallel it leaves
**text notes about your grammar mistakes**. The notes are only shown on screen, never
spoken aloud.

```
Audio (you) → STT → LLM → TTS → Audio reply + grammar notes
```

The project is a pet project with a learning goal: a **microservice architecture**
with a meaningful split — auth, users, an orchestrator, and three AI workers that talk
over RabbitMQ.

## Features

- **Two conversation modes**
  - *Walkie-talkie*: record a full voice message, send it, get back a voiced reply plus notes.
  - *Realtime call*: stream your microphone over a WebSocket. A server-side VAD detects
    when you stop speaking, the reply streams token by token, and each finished sentence
    is voiced right away, so the tutor starts talking before the model has finished writing.
- **Grammar-only corrections**: each mistake comes back as `you_said` / `better` / `note`
  and is classified into a catalog of grammar topics (CEFR A1–B2).
- **Mistakes overview**: all your mistakes grouped by grammar topic, across sessions.
- **Session history**: past sessions with transcripts, corrections and audio for each turn.
- **Auth**: email + password sign-up, Google sign-in, RS256 JWT access/refresh tokens.

## Architecture

```
                         ┌──────────────┐
                         │   Angular    │
                         │   frontend   │
                         └──────┬───────┘
              HTTP / WebSocket  │
        ┌───────────────────────┼────────────────────────┐
        ▼                       ▼                        ▼
┌───────────────┐     ┌───────────────────┐     ┌───────────────┐
│ auth-service  │     │ orchestrator-     │     │ user-service  │
│ :8001         │     │ service :8002     │     │ :8000         │
│ identity, JWT │     │ sessions, history │     │ profiles      │
└───────┬───────┘     └─────────┬─────────┘     └───────┬───────┘
     Postgres        Postgres · Redis · disk         Postgres
                                │
                     RabbitMQ RPC queues
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
  ┌───────────────┐     ┌───────────────┐     ┌───────────────┐
  │ stt-service   │     │ llm-service   │     │ tts-service   │
  │ faster-whisper│     │ structured    │     │ Piper         │
  │ stt.rpc       │     │ output        │     │ tts.rpc       │
  └───────────────┘     │ llm.rpc       │     └───────────────┘
                        └───────┬───────┘
                                ▼
                        ┌───────────────┐
                        │ LiteLLM proxy │ → any LLM provider
                        │ :4000         │
                        └───────────────┘
```

Key design decisions:

- **The LLM is stateless.** The orchestrator owns the session history (Postgres, with the
  hot context cached in Redis) and sends the full, bounded message history every turn.
- **Structured output.** The LLM returns two separate parts: `spoken_reply` goes to TTS,
  `corrections[]` stay text-only. A Pydantic schema guarantees they never mix.
- **Verbatim STT.** Whisper runs without text normalization, so grammar mistakes survive
  into the transcript.
- **No vendor lock-in.** All LLM calls go through a **LiteLLM** gateway. The model is an
  alias configured in the LiteLLM UI, so switching provider is a config change, not a
  code change. Provider keys live only inside LiteLLM.
- **Database per service** and **asymmetric JWT**: auth-service signs tokens with the
  private key, other services verify them with the public key, with no shared secret and
  no callback to auth-service.

## Services

| Service | What it does | Tech | Port |
|---|---|---|---|
| [`frontend`](frontend) | Web UI: login/sign-up, sessions, realtime call, mistakes notes | Angular 20, TypeScript | 4200 |
| [`auth-service`](services/auth-service) | Identity, password + Google OAuth login, issues RS256 JWTs | FastAPI, PostgreSQL, Alembic | 8001 |
| [`user-service`](services/user-service) | User profiles | FastAPI, PostgreSQL, Alembic | 8000 |
| [`orchestrator-service`](services/orchestrator-service) | Sessions, turns, history, the STT → LLM → TTS pipeline, realtime WebSocket call, mistakes | FastAPI, PostgreSQL, Redis, RabbitMQ, webrtcvad | 8002 |
| [`stt-service`](services/stt-service) | Speech-to-text worker (`stt.rpc`) | faster-whisper | — |
| [`llm-service`](services/llm-service) | LLM worker (`llm.rpc`): spoken reply + grammar corrections | Anthropic SDK → LiteLLM | — |
| [`tts-service`](services/tts-service) | Text-to-speech worker (`tts.rpc`) | Piper (`en_US-lessac-medium`) | — |
| [`litellm`](services/litellm) | LLM gateway with its own Postgres | LiteLLM proxy | 4000 |

Infrastructure ports: Postgres `5432` (user), `5433` (auth), `5434` (orchestrator),
`5435` (LiteLLM) · Redis `6379` · RabbitMQ `5672` (management UI `15672`).

Each service has its own README with endpoints, config and details.

## Getting started

### Prerequisites

- Docker with Docker Compose
- Node.js + npm (for the frontend)
- OpenSSL (to generate the JWT key pair)

### 1. Create the shared Docker network

```bash
docker network create webeng
```

### 2. Generate the JWT key pair

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out private.pem
openssl rsa -in private.pem -pubout -out public.pem
```

### 3. Create a root `.env`

The root compose reads these variables from `.env` in the repo root (it is git-ignored):

```dotenv
# JWT (paste the PEM contents, in quotes)
JWT_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----..."
JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----..."

# Google sign-in (optional; needed only for "Sign in with Google")
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# LiteLLM
LITELLM_MASTER_KEY=sk-...        # admin key for the LiteLLM UI
LLM_API_KEY=sk-...               # LiteLLM virtual key used by llm-service
LLM_MODEL=tutor-default          # LiteLLM model alias
```

For Google sign-in, add `http://localhost:8001/auth/google/callback` as a redirect URI
of your OAuth client in Google Cloud Console.

### 4. Start the backend

```bash
docker compose up --build
```

Each API waits for its database, runs `alembic upgrade head`, then starts. The first STT
start downloads the Whisper model (needs internet).

### 5. Configure the LLM in LiteLLM

Open http://localhost:4000/ui, log in with `LITELLM_MASTER_KEY`, add a provider and its
API key, create a model named after your `LLM_MODEL` alias (e.g. `tutor-default`), and
create a virtual key for `LLM_API_KEY`.

### 6. Start the frontend

```bash
cd frontend
npm install
npm start
```

Open http://localhost:4200. The dev server proxies `/api/auth` to auth-service and
`/api/sessions`, `/api/mistakes` to the orchestrator (WebSocket included), see
[`proxy.conf.json`](frontend/proxy.conf.json).

## Development

Python services follow one layout:

```
app/
  routes/        # FastAPI routers (thin)
  services/      # business logic
  repositories/  # data access (SQLAlchemy queries)
  models/        # SQLAlchemy ORM models
  schemas/       # Pydantic request/response models
  utils/         # jwt, dependencies, middleware, ...
  conf/          # settings from env
migrations/      # Alembic
```

Checks to run in a service folder before committing:

```bash
ruff format --check .
ruff check .
mypy .
pytest -m "not integration"
```

Conventions: English for all code, comments, docs and commit messages; `snake_case`
functions; type hints everywhere; `async` for I/O.

## Tech stack

**Backend:** Python, FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL, Redis,
RabbitMQ (aio-pika), PyJWT (RS256), webrtcvad
**AI:** faster-whisper (STT), LiteLLM + Anthropic SDK (LLM, structured output), Piper (TTS)
**Frontend:** Angular 20, TypeScript
**Infra:** Docker, Docker Compose
