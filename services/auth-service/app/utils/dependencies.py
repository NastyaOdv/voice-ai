import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyCookie
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.async_session_manager import get_db_async_session
from app.models import User
from app.repositories import user_repo
from app.utils.jwt import decode_token

# Auth is carried by the httpOnly `access_token` cookie set on login/register.
cookie_scheme = APIKeyCookie(name="access_token")


async def get_current_user(
    token: str = Depends(cookie_scheme),
    db: AsyncSession = Depends(get_db_async_session),
) -> User:
    """Resolve the current user from the access-token cookie."""
    try:
        payload = decode_token(token)
    except Exception as exc:  # jwt raises several exception types
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not an access token"
        )

    user = await user_repo.get_user_by_id(db, uuid.UUID(payload["sub"]))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    return user
