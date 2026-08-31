from fastapi import Response

from app.conf.config import get_settings
from app.schemas.auth import TokenPair

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


def set_auth_cookies(response: Response, tokens: TokenPair) -> None:
    settings = get_settings()
    response.set_cookie(
        ACCESS_COOKIE,
        tokens.access_token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")
