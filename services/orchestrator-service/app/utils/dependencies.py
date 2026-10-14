import uuid

from fastapi import Depends, HTTPException, Request, WebSocket, WebSocketException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.async_session_manager import get_db_async_session
from app.services.mistake_service import MistakeService
from app.services.session_service import SessionService
from app.utils.jwt import decode_token


def get_current_user_id(request: Request) -> uuid.UUID:
    """Return the user id put on the request by the `jwt_auth` middleware.

    Raises 401 when there was no valid access token on the request.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    return uuid.UUID(str(user_id))


def get_session_service(
    request: Request, db: AsyncSession = Depends(get_db_async_session)
) -> SessionService:
    return SessionService(
        db=db, redis=request.app.state.redis, broker=request.app.state.broker
    )


async def get_current_user_id_ws(websocket: WebSocket) -> uuid.UUID:
    """WebSocket counterpart of `get_current_user_id`.

    The HTTP `jwt_auth` middleware does not run for websocket connections, so the
    access token is validated here directly: read the `access_token` cookie, verify it
    with auth-service's public key, and require an `access`-type token. Any failure
    closes the handshake with policy-violation (1008).
    """
    token = websocket.cookies.get("access_token")
    if not token:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Not authenticated"
        )
    try:
        payload = decode_token(token)
    except Exception as exc:  # jwt raises several exception types
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token"
        ) from exc
    if payload.get("type") != "access":
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Not an access token"
        )
    return uuid.UUID(str(payload["sub"]))


def get_session_service_ws(
    websocket: WebSocket, db: AsyncSession = Depends(get_db_async_session)
) -> SessionService:
    """WebSocket counterpart of `get_session_service` (state lives on `websocket.app`)."""
    return SessionService(
        db=db, redis=websocket.app.state.redis, broker=websocket.app.state.broker
    )


def get_mistake_service(
    db: AsyncSession = Depends(get_db_async_session),
) -> MistakeService:
    return MistakeService(db=db)
