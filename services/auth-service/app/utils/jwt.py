import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import jwt

from app.conf.config import get_settings


@lru_cache
def load_private_key() -> str:
    return Path(get_settings().jwt_private_key_path).read_text()


@lru_cache
def load_public_key() -> str:
    return Path(get_settings().jwt_public_key_path).read_text()


def create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, load_private_key(), algorithm=get_settings().jwt_algorithm)


def create_access_token(subject: str) -> str:
    return create_token(
        subject,
        "access",
        timedelta(minutes=get_settings().access_token_expire_minutes),
    )


def create_refresh_token(subject: str) -> str:
    return create_token(
        subject, "refresh", timedelta(days=get_settings().refresh_token_expire_days)
    )


def decode_token(token: str) -> dict[str, Any]:
    """Verify signature + expiry with the public key. Raises on any problem."""
    return jwt.decode(token, load_public_key(), algorithms=[get_settings().jwt_algorithm])
