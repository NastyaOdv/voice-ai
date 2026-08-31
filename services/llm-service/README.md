# llm-service

LLM worker. Consumes the `llm.rpc` queue, calls **Anthropic Claude** with the session
history, and replies with a **structured** result. Not an HTTP service — a RabbitMQ worker.

## Contract

Request → reply on the queue `llm.rpc`:

```
{ "messages": [{"role","content"}, ...] }
  →  { "spoken_reply": "...", "corrections": [{"you_said","better","note"}] }
```

`spoken_reply` is voiced by TTS; `corrections` are text-only grammar notes. The split is
guaranteed by structured output (`messages.parse` + a Pydantic schema), so the two never mix.

On failure it replies `{ "error": "<message>" }`.

## How it works

- Official `anthropic` SDK (`AsyncAnthropic`), non-blocking.
- The orchestrator sends the full history each turn (the LLM is stateless). The worker
  splits out any `system` messages into Claude's `system` field and passes user/assistant
  turns as `messages`.
- **Thinking disabled** — short structured task; keeps latency/cost down and the JSON
  inside `max_tokens`.
- A `refusal` (or missing structured output) returns a safe spoken line instead of breaking
  the pipeline.

## Config (env)

| Var               | Default          | Notes                                   |
|-------------------|------------------|-----------------------------------------|
| `RABBITMQ_URL`    | local            | broker to consume from                  |
| `LLM_QUEUE`       | `llm.rpc`        | request queue name                      |
| `LLM_MODEL`       | `claude-opus-5`  | any Claude model id                     |
| `LLM_MAX_TOKENS`  | `1024`           | reply cap                               |
| `ANTHROPIC_API_KEY` | —              | required; read by the SDK               |

## Run

```bash
docker network create webeng   # once, shared by all services
docker compose up --build
```

Set `ANTHROPIC_API_KEY` (and optionally `LLM_MODEL`) in the repo-root `.env` so compose
passes them in. The worker retries until RabbitMQ is reachable.
