"""Minimal Google OAuth2 Authorization Code client (done by hand with httpx).

Flow: build_authorization_url -> user consents at Google -> Google redirects back
with `code` -> exchange_code -> fetch_userinfo. The httpx client is the app-wide one
created in the lifespan and passed in by the caller.
"""
from typing import Any
from urllib.parse import urlencode

import httpx

from app.conf.config import get_settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def build_authorization_url(state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code(client: httpx.AsyncClient, code: str) -> dict[str, Any]:
    """Exchange the authorization code for Google access/id tokens."""
    settings = get_settings()
    data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    response = await client.post(GOOGLE_TOKEN_URL, data=data)
    response.raise_for_status()
    return response.json()


async def fetch_userinfo(client: httpx.AsyncClient, access_token: str) -> dict[str, Any]:
    """Fetch the user's profile (sub, email, name) from Google."""
    headers = {"Authorization": f"Bearer {access_token}"}
    response = await client.get(GOOGLE_USERINFO_URL, headers=headers)
    response.raise_for_status()
    return response.json()
