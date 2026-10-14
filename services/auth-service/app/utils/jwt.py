import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization

from app.conf.config import get_settings


def normalize_pem(raw: str) -> str:
    """Accept a PEM key with real newlines or escaped `\\n` (as stored in .env/compose)."""
    return raw.replace("\\n", "\n").strip()


@lru_cache
def load_private_key() -> str:
    key = normalize_pem(get_settings().jwt_private_key)
    if not key:
        raise RuntimeError("JWT_PRIVATE_KEY is not configured")
    return key


@lru_cache
def load_public_key() -> str:
    """Derive the public key from the private one (used to verify our own tokens)."""
    private_key = serialization.load_pem_private_key(
        load_private_key().encode(), password=None
    )
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


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
