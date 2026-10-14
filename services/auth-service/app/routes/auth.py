import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.conf.config import get_settings
from app.db.async_session_manager import get_db_async_session
from app.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UserIdentity,
)
from app.services import google_oauth
from app.services.auth_service import AuthService
from app.utils.cookies import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from app.utils.dependencies import get_current_user
from app.utils.exceptions import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidToken,
    PasswordNotSet,
)

router = APIRouter(prefix="/auth", tags=["auth"])

STATE_COOKIE = "oauth_state"


def get_auth_service(db: AsyncSession = Depends(get_db_async_session)) -> AuthService:
    return AuthService(db)


@router.post(
    "/register", response_model=UserIdentity, status_code=status.HTTP_201_CREATED
)
async def register(
    data: RegisterRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> User:
    try:
        user = await service.register(data.email, data.password)
    except EmailAlreadyRegistered as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from exc
    # Tokens go into httponly cookies only; the body carries the user identity.
    set_auth_cookies(response, service.issue_tokens(user))
    return user


@router.post("/login", response_model=UserIdentity)
async def login(
    data: LoginRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> User:
    try:
        user = await service.authenticate(data.email, data.password)
    except InvalidCredentials as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        ) from exc
    set_auth_cookies(response, service.issue_tokens(user))
    return user


@router.get("/google/login")
async def google_login() -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(google_oauth.build_authorization_url(state))
    # CSRF protection: remember the state in an httponly cookie, check it on callback.
    response.set_cookie(STATE_COOKIE, state, httponly=True, max_age=600, samesite="lax")
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str,
    state: str,
    service: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    """Finish the Google OAuth dance and hand control back to the SPA.

    This is a top-level browser navigation, so we set the auth cookies and redirect
    to the frontend (never return JSON, which the browser would just display).
    """
    frontend_url = get_settings().frontend_url
    expected_state = request.cookies.get(STATE_COOKIE)
    if expected_state is None or not secrets.compare_digest(expected_state, state):
        return RedirectResponse(f"{frontend_url}/login?error=google")

    user = await service.login_with_google(code, request.app.state.http_client)
    tokens = service.issue_tokens(user)
    response = RedirectResponse(f"{frontend_url}/sessions")
    set_auth_cookies(response, tokens)
    response.delete_cookie(STATE_COOKIE, path="/")
    return response


@router.post("/refresh", response_model=UserIdentity)
async def refresh(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> User:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token"
        )
    try:
        user = await service.refresh_tokens(refresh_token)
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc
    set_auth_cookies(response, service.issue_tokens(user))
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout() -> Response:
    """Log out by clearing the auth cookies."""
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)
    return response


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    try:
        await service.change_password(user, data.current_password, data.new_password)
    except PasswordNotSet as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account has no password (Google sign-in)",
        ) from exc
    except InvalidCredentials as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserIdentity)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
