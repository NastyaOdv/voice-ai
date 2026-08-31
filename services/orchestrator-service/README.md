# orchestrator-service

The brain of the voice pipeline: `Audio → STT → LLM → TTS → Audio + grammar notes`.
Holds session history, calls the STT/LLM/TTS workers over RabbitMQ (RPC), caches the
hot session context in Redis, stores audio on local disk, keeps everything durable in
Postgres.

Python + FastAPI, async SQLAlchemy 2.0 (psycopg), Alembic, Redis, aio-pika.

## Pipeline (per user turn)

1. Receive the user's audio (`POST /sessions/{id}/turns`).
2. **STT** over queue `stt.rpc` → transcript (verbatim).
3. **LLM** over queue `llm.rpc` → `{ spoken_reply, corrections[] }` (structured).
4. **TTS** over queue `tts.rpc` on `spoken_reply` only → audio.
5. Persist turns + corrections (Postgres), refresh context (Redis), return the reply
   audio URL + transcript + corrections. Corrections are text-only, never voiced.

The LLM is stateless: the orchestrator sends the full message history every turn.

## Endpoints

| Method | Path                                     | Purpose                         |
|--------|------------------------------------------|---------------------------------|
| POST   | `/sessions`                              | Start a session                 |
| POST   | `/sessions/{id}/turns`                   | Upload audio → reply + notes    |
| GET    | `/sessions/{id}`                         | Session with its turns          |
| POST   | `/sessions/{id}/close`                   | Close a session                 |
| GET    | `/sessions/{id}/turns/{turn_id}/audio`   | Fetch a turn's audio (wav)      |
| GET    | `/health`                                | Liveness                        |

All except `/health` require a Bearer access token from auth-service (validated by the
`jwt_auth` middleware against auth's public key).

## Ports

- API: http://localhost:8002 (Swagger at `/docs` in dev)
- Postgres: localhost:5434 · Redis: localhost:6379 · RabbitMQ: localhost:5672 (UI 15672)

## Run

```bash
docker network create webeng   # once, shared by all services
docker compose up --build
```

On start the API waits for Postgres/RabbitMQ/Redis, runs `alembic upgrade head`
(creates `or_sessions`, `or_turns`, `or_corrections`), then serves on :8002.

## Status

The pipeline is wired end-to-end **up to the queue boundary**. The `stt.rpc`,
`llm.rpc`, `tts.rpc` workers do not exist yet — until they do, `POST .../turns` will
block waiting for a reply. Building those three worker services is the next step.

### Message contracts (worker request → reply)

- `stt.rpc`: `{ "audio_b64": "..." }` → `{ "text": "..." }`
- `llm.rpc`: `{ "messages": [{"role","content"}, ...] }` → `{ "spoken_reply": "...", "corrections": [{"you_said","better","note"}] }`
- `tts.rpc`: `{ "text": "..." }` → `{ "audio_b64": "..." }`
