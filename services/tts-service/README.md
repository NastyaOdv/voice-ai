# tts-service

Text-to-speech worker for the English-tutor pipeline. Consumes the **`tts.rpc`** queue
and voices the tutor's `spoken_reply`.

- **Engine:** [Piper](https://github.com/rhasspy/piper) — a fast, CPU-friendly neural
  TTS. Voice: `en_US-lessac-medium`, baked into the image (offline, deterministic).
- **Transport:** RabbitMQ RPC (request/reply), same pattern as `stt-service`.

## Contract

```jsonc
// request
{ "text": "Nice! Where do you study?" }
// reply
{ "audio_b64": "<base64 WAV, mono 16-bit PCM>" }
```

The orchestrator calls this best-effort with an 8s timeout; if the worker is down the
assistant reply is still saved (text only, no audio).

## Run

Part of the root `docker-compose.yml`. Standalone:

```bash
docker network create webeng   # once
docker compose up --build
```

## Config (env)

| Var           | Default                                   | Meaning                         |
|---------------|-------------------------------------------|---------------------------------|
| `RABBITMQ_URL`| `amqp://guest:guest@localhost:5672/`      | Broker URL                      |
| `TTS_QUEUE`   | `tts.rpc`                                  | Queue this worker consumes      |
| `MODEL_PATH`  | `/app/voices/en_US-lessac-medium.onnx`    | Piper voice (`.onnx`); config is `<MODEL_PATH>.json` |

To swap the voice, change `MODEL_PATH` and bake a different `.onnx` + `.onnx.json`
(from [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)).
