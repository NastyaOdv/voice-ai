"""Tests for the realtime call WebSocket (E2 auth + E3 VAD-driven pipeline)."""
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from starlette.websockets import WebSocketDisconnect

from app.routes import call as call_route
from app.utils import dependencies
from app.utils.exceptions import NotSessionOwner
from tests.conftest import FakeSession, FakeSessionService


def test_call_ws_rejects_connection_without_token(client):
    """No `access_token` cookie -> handshake closed with policy-violation (1008)."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/sessions/{uuid.uuid4()}/call"):
            pass
    assert exc_info.value.code == 1008


def test_call_ws_rejects_non_owner(app, client):
    """A valid token but a session owned by someone else -> closed with 1008."""
    user_id = uuid.uuid4()

    class DenyingService:
        async def get_owned_session(self, session_id, user_id):
            raise NotSessionOwner()

    app.dependency_overrides[dependencies.get_current_user_id_ws] = lambda: user_id
    app.dependency_overrides[dependencies.get_session_service_ws] = DenyingService
    try:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/sessions/{uuid.uuid4()}/call"):
                pass
        assert exc_info.value.code == 1008
    finally:
        app.dependency_overrides.clear()


class _EndOnFirstFrameVad:
    """Fake endpointer: the first binary frame closes one utterance immediately."""

    def __init__(self) -> None:
        self._fired = False

    def feed(self, data: bytes) -> Iterator[tuple[str, bytes | None]]:
        if not self._fired:
            self._fired = True
            yield ("start", None)
            yield ("end", b"\x00\x00" * 160)  # 10 ms of PCM16 silence


class _PipelineService(FakeSessionService):
    """Owns the session and yields a canned realtime pipeline result."""

    async def run_turn_realtime(
        self, session_id: uuid.UUID, user_id: uuid.UUID, audio_bytes: bytes
    ) -> AsyncIterator[dict]:
        yield {"type": "user_turn", "text": "i has a apple"}
        yield {"type": "reply_delta", "text": "Nice!"}
        yield {"type": "audio_chunk", "text": "Nice!", "audio_b64": "AAAA"}
        yield {"type": "assistant_done", "text": "Nice!"}
        yield {"type": "corrections", "corrections": []}


def test_call_ws_endpoints_utterance_and_forwards_pipeline(app, client, monkeypatch):
    """A binary frame that VAD closes -> speech_start/_end + forwarded pipeline events."""
    user_id = uuid.uuid4()
    monkeypatch.setattr(call_route, "make_endpointer", _EndOnFirstFrameVad)
    app.dependency_overrides[dependencies.get_current_user_id_ws] = lambda: user_id
    app.dependency_overrides[dependencies.get_session_service_ws] = (
        lambda: _PipelineService(user_id)
    )
    try:
        with client.websocket_connect(f"/sessions/{uuid.uuid4()}/call") as ws:
            ws.send_bytes(b"\x00\x00" * 320)
            assert ws.receive_json() == {"type": "speech_start"}
            assert ws.receive_json() == {"type": "speech_end"}
            assert ws.receive_json()["type"] == "user_turn"
            assert ws.receive_json()["type"] == "reply_delta"
            assert ws.receive_json()["type"] == "audio_chunk"
            assert ws.receive_json()["type"] == "assistant_done"
            assert ws.receive_json()["type"] == "corrections"
            ws.send_text("bye")
    finally:
        app.dependency_overrides.clear()


def test_call_ws_closes_when_session_not_active(app, client):
    """Opening a call on a closed session is refused with 1008."""
    user_id = uuid.uuid4()

    class ClosedSessionService:
        async def get_owned_session(self, session_id, user_id):
            row = FakeSession(user_id)
            row.status = "closed"
            return row

    app.dependency_overrides[dependencies.get_current_user_id_ws] = lambda: user_id
    app.dependency_overrides[dependencies.get_session_service_ws] = ClosedSessionService
    try:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/sessions/{uuid.uuid4()}/call"):
                pass
        assert exc_info.value.code == 1008
    finally:
        app.dependency_overrides.clear()
