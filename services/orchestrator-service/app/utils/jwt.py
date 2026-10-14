"""Verify JWTs issued by auth-service using its RS256 public key.

The public key is provided via env (JWT_PUBLIC_KEY) — no shared secret, no call to
auth per request, no runtime key fetch. auth holds the matching private key.
"""
from functools import lru_cache
from typing import Any

import jwt

from app.conf.config import get_settings


def normalize_pem(raw: str) -> str:
    """Accept a PEM key with real newlines or escaped `\\n` (as stored in .env/compose)."""
    return raw.replace("\\n", "\n").strip()


@lru_cache
def load_public_key() -> str:
    key = normalize_pem(get_settings().jwt_public_key)
    if not key:
        raise RuntimeError("JWT_PUBLIC_KEY is not configured")
    return key


def decode_token(token: str) -> dict[str, Any]:
    """Verify signature + expiry with auth-service's public key. Raises on any problem."""
    return jwt.decode(token, load_public_key(), algorithms=[get_settings().jwt_algorithm])
