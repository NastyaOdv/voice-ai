# E4 — Streaming LLM reply + per-sentence TTS

> Level 2, epic E4. Builds on E2 (WS + auth) and E3 (server VAD → non-streaming reply).

## Goal

The tutor starts **speaking while the LLM is still writing**: `spoken_reply` streams as
tokens → finished sentences go to TTS immediately → audio chunks play back in order.
`corrections` are computed as a **separate pass** and arrive as their own event.

## Locked decisions

1. **Two LLM calls per turn** (split, decided with the user):
   - `stream_reply` — plain text stream (`messages.stream`, no structured output),
     system prompt = "conversational reply only".
   - `detect_corrections` — structured (`messages.parse`) with a corrections-only schema,
     runs concurrently (`asyncio.create_task`). Prompt/history caching offsets the 2nd call.
2. **LLM worker gets a mode flag**: payload `mode: "stream_reply"` → worker iterates deltas
   and publishes many `{"delta": "..."}` to `reply_to`, ending with `{"done": true, "text": full}`
   (the existing `call_stream` protocol). No flag → existing structured behavior (v1 untouched).
3. **Sentence segmentation in the orchestrator** (`utils/text.py`): accumulate deltas, cut on
   `.!?…`/newline, flush the remainder at stream end.
4. **Per-sentence TTS, contract unchanged**: each finished sentence → `broker.call(TTS_QUEUE, {text})`.
   For history, concatenate the WAV chunks into one and save it on the assistant turn
   (`utils/audio.py: concat_wavs`) so the v1 transcript view can still replay it.
5. **Audio transport to client**: `{"type":"audio_chunk","audio_b64":...}` over the WS + a
   Web Audio playback queue (decodeAudioData + chained source nodes) for gapless playback.
   Plus `reply_delta` for live "typing" text.

## Out of scope for E4
- Barge-in / interruption (E6) — mic still not processed while the tutor speaks.
- Internal TTS streaming (Piper is fast enough per sentence).

## Tasks

| # | Task | Tests |
|---|------|-------|
| T4.1 | `utils/text.py` — `SentenceAggregator.feed()/flush()` | unit: deltas mid-sentence, several per delta, `.!?`, remainder |
| T4.2 | `utils/audio.py` — `concat_wavs()` | unit: two WAVs → summed frames |
| T4.3 | llm: `stream_reply()` + `detect_corrections()`; worker branch `mode=stream_reply` | unit on `stream_reply` w/ mock client; worker = manual/integration |
| T4.4 | `session_service.run_turn_realtime()` — events `user_turn → reply_delta*/audio_chunk* → assistant_done → corrections`; persist turn/corrections/mistakes, concat audio, Redis | unit on event order w/ fake broker; DB = e2e |
| T4.5 | `call.py` → `run_turn_realtime`, update protocol doc | update WS test (fake service) |
| T4.6 | `realtime-call.ts` — playback queue, `reply_delta`/`audio_chunk`/`assistant_done`/`corrections`, "Tutor speaking" phase | ng build |
| T4.7 | config: reply-only + corrections prompts, token limits | — |
| T4.8 | update `CLAUDE.md` Stack notes | — |

Order: T4.1 → T4.2 (pure utils, TDD) → T4.3 (stream worker) → T4.4/T4.5 (orchestration + WS) → T4.6 (frontend).

## Risks
- 2 LLM calls per turn (offset by caching).
- Minor gaps between concatenated per-sentence audio — acceptable.
