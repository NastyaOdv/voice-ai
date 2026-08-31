"""Realtime call WebSocket (Level 2).

A single connection carries one live "call": the client streams microphone audio as
binary PCM frames (16-bit little-endian, mono, 16 kHz) and receives back structured
JSON events. A server-side VAD decides when the learner has stopped talking — that is
what replaces the manual "Stop" button of v1.

Protocol (E4 — streamed reply, per-sentence audio):
  client -> server : binary frames (raw PCM16/16k), text `bye` to hang up
  server -> client :
    - `{"type": "speech_start"}`                 when the learner starts speaking
    - `{"type": "speech_end"}`                   when a silence closes the utterance
    - `{"type": "user_turn", ...}`               transcript (after STT)
    - `{"type": "reply_delta", "text": ...}`     streamed reply tokens
    - `{"type": "audio_chunk", "audio_b64": ...}` voiced sentence (as each completes)
    - `{"type": "assistant_done", ...}`          full reply persisted
    - `{"type": "corrections", ...}`             grammar notes (parallel second pass)

On each detected utterance we run `run_turn_realtime`: the spoken reply streams token by
token and each finished sentence is voiced immediately, so the tutor starts speaking
before the model has finished writing; corrections are computed by a separate call.

Auth: the HTTP `jwt_auth` middleware does not run for websockets, so the token is
validated in `get_current_user_id_ws` and session ownership is checked here before the
handshake is accepted; either failure closes with policy-violation (1008).
"""
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from starlette.websockets import WebSocketState

from app.conf.config import get_settings
from app.logger.logger_config import logger
from app.services.session_service import SessionService
from app.utils.audio import pcm16_to_wav
from app.utils.dependencies import get_current_user_id_ws, get_session_service_ws
from app.utils.exceptions import NotSessionOwner, SessionNotFound
from app.utils.vad import VadEndpointer

router = APIRouter(prefix="/sessions", tags=["call"])

SAMPLE_RATE = 16000


def make_endpointer() -> VadEndpointer:
    """Factory for the per-connection VAD (a seam tests can monkeypatch)."""
    settings = get_settings()
    return VadEndpointer(
        sample_rate=SAMPLE_RATE,
        aggressiveness=settings.vad_aggressiveness,
        end_silence_ms=settings.vad_end_silence_ms,
    )


@router.websocket("/{session_id}/call")
async def call(
    websocket: WebSocket,
    session_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id_ws),
    service: SessionService = Depends(get_session_service_ws),
) -> None:
    # Authorize the session before accepting: a stranger never reaches the audio loop.
    try:
        session_row = await service.get_owned_session(session_id, user_id)
    except (SessionNotFound, NotSessionOwner):
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Session not found"
        )
        return
    if session_row.status != "active":
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Session is closed"
        )
        return

    await websocket.accept()
    logger.info(f"Call WS open: session={session_id} user={user_id}")
    endpointer = make_endpointer()
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            if (data := message.get("bytes")) is not None:
                for event, utterance in endpointer.feed(data):
                    if event == "start":
                        await websocket.send_json({"type": "speech_start"})
                    elif event == "end" and utterance:
                        await websocket.send_json({"type": "speech_end"})
                        wav = pcm16_to_wav(utterance, SAMPLE_RATE)
                        try:
                            async for turn_event in service.run_turn_realtime(
                                session_id, user_id, wav
                            ):
                                await websocket.send_json(turn_event)
                        except Exception:
                            # One failed turn must not drop the whole call.
                            logger.exception("Realtime turn failed; keeping call open")
                            await websocket.send_json(
                                {"type": "error", "message": "That turn failed — keep going."}
                            )
                        # Fresh endpointer: audio buffered while the pipeline ran must
                        # not bleed into the next utterance and misfire.
                        endpointer = make_endpointer()
            elif (text := message.get("text")) is not None:
                if text == "bye":
                    break
    except WebSocketDisconnect:
        pass
    finally:
        logger.info(f"Call WS close: session={session_id}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
