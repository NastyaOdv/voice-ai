"""Verify JWTs issued by auth-service using its RS256 public key.

The public key is fetched once from auth-service's `/auth/public-key` endpoint (using
the app-wide httpx client) and cached in memory.
"""
from typing import Any

import httpx
import jwt

from app.conf.config import get_settings

key_cache: dict[str, str] = {}


async def get_public_key(client: httpx.AsyncClient) -> str:
    if "pem" not in key_cache:
        response = await client.get(get_settings().auth_public_key_url)
        response.raise_for_status()
        key_cache["pem"] = response.json()["public_key"]
    return key_cache["pem"]


async def decode_token(token: str, client: httpx.AsyncClient) -> dict[str, Any]:
    public_key = await get_public_key(client)
    return jwt.decode(token, public_key, algorithms=[get_settings().jwt_algorithm])
