# llm-service

LLM worker. Consumes the `llm.rpc` queue, calls the **LiteLLM proxy** with the session
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

- All calls go through the **LiteLLM proxy** (the LLM gateway), never to a provider
  directly. `LLM_BASE_URL` points at the proxy and `LLM_API_KEY` is a LiteLLM *virtual
  key* — the real provider keys live inside LiteLLM and are never seen by this service.
- `LLM_MODEL` is a LiteLLM **public model name (alias)**, not a provider model id. Which
  provider and model it resolves to is configured in the LiteLLM UI
  (http://localhost:4000/ui), so switching models or providers is a config change, not a
  code change.
- The client is the `anthropic` SDK (`AsyncAnthropic`), pointed at LiteLLM's
  Anthropic-compatible `/v1/messages` endpoint. It is the **wire format only** — the
  vendor behind the alias is LiteLLM's business.
- The orchestrator sends the history each turn (the LLM is stateless, and the window is
  bounded by the orchestrator's `LLM_HISTORY_MAX_PAIRS`). The worker splits out any
  `system` messages into the `system` field and passes user/assistant turns as `messages`.
- **Thinking disabled** — short structured task; keeps latency/cost down and the JSON
  inside `max_tokens`.
- A `refusal` (or missing structured output) returns a safe spoken line instead of breaking
  the pipeline.

> **Caching caveat.** `cache_control` and `thinking` are Anthropic-format fields. When the
> alias routes to a provider that does not honour them (e.g. Gemini) they are silently
> ignored and every call is billed as uncached — the `[…] usage:` log line shows
> `cache_read=0`. Check which provider the alias resolves to before reading cache numbers.

## Config (env)

| Var              | Default                 | Notes                                        |
|------------------|-------------------------|----------------------------------------------|
| `RABBITMQ_URL`   | local                   | broker to consume from                       |
| `LLM_QUEUE`      | `llm.rpc`               | request queue name                           |
| `LLM_MODEL`      | `tutor-default`         | LiteLLM public model name (alias)            |
| `LLM_MAX_TOKENS` | `1024`                  | reply cap                                    |
| `LLM_BASE_URL`   | `http://localhost:4000` | LiteLLM proxy endpoint                       |
| `LLM_API_KEY`    | —                       | LiteLLM virtual key (`sk-…`), required       |

No provider API key belongs here. Add providers and their keys in the LiteLLM UI.

## Run

```bash
docker network create webeng   # once, shared by all services
docker compose up --build
```

Set `LLM_API_KEY` (and optionally `LLM_MODEL`) in the repo-root `.env` so compose passes
them in. The worker retries until RabbitMQ is reachable.

## Observability

Each call logs two lines — context size before the request and real token usage after:

```
[structured] context: turns=8 sys_tok~1688 hist_tok~922 user_tok~94
[structured] usage: input=2671 cache_write=0 cache_read=0 output=344 total_input=2671 cache_hit=0%
```

`input` counts only tokens that were *not* served from cache, so the real input size is
`total_input` (input + cache_write + cache_read).
