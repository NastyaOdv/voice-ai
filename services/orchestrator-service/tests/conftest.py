"""Shared test fixtures.

The realtime call WS is authenticated per-connection (no HTTP middleware runs for
websockets), so these tests build the real app but override the WS dependencies to
avoid touching Postgres/Redis/RabbitMQ. The app's lifespan (which connects to the
broker) is intentionally NOT entered — `TestClient.websocket_connect` works without it.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.app import get_application


@pytest.fixture
def app():
    return get_application()


@pytest.fixture
def client(app):
    return TestClient(app)


class FakeSession:
    """Minimal stand-in for an ORM Session row for ownership checks."""

    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.status = "active"


class FakeSessionService:
    """A SessionService whose `get_owned_session` always succeeds for `user_id`."""

    def __init__(self, user_id: uuid.UUID) -> None:
        self._user_id = user_id

    async def get_owned_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> FakeSession:
        return FakeSession(user_id)
