# stt-service

Speech-to-text worker. Consumes the `stt.rpc` queue, transcribes audio with
**faster-whisper**, and replies. Not an HTTP service — a RabbitMQ worker.

## Contract

Request → reply on the queue `stt.rpc`:

```
{ "audio_b64": "<base64 audio bytes>" }  →  { "text": "<verbatim transcript>" }
```

On failure it replies `{ "error": "<message>" }`.

## How it works

- One `WhisperModel` is loaded at startup and reused (warm start).
- Transcription runs in a thread (`asyncio.to_thread`) so the event loop stays free.
- `prefetch=1` — one clip at a time (the model is the bottleneck).
- **Verbatim**: no cleanup, so grammar mistakes survive into the transcript.

## Config (env)

| Var            | Default   | Notes                                        |
|----------------|-----------|----------------------------------------------|
| `RABBITMQ_URL` | local     | broker to consume from                       |
| `STT_QUEUE`    | `stt.rpc` | request queue name                           |
| `MODEL_SIZE`   | `base`    | `tiny`/`base`/`small`/`medium`; `*.en` = EN  |
| `DEVICE`       | `cpu`     | `cpu` or `cuda`                              |
| `COMPUTE_TYPE` | `int8`    | `int8` (CPU) / `float16` (GPU)               |
| `BEAM_SIZE`    | `5`       | decoding beam size                           |

## Run

```bash
docker network create webeng   # once, shared by all services
docker compose up --build
```

First start downloads the model into the `stt_model_cache` volume (needs internet).
The worker retries until RabbitMQ (in orchestrator-service's compose) is reachable.
