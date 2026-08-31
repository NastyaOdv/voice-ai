import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.repositories import user_repo
from app.schemas.auth import TokenPair
from app.services import google_oauth
from app.utils.exceptions import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidToken,
    PasswordNotSet,
)
from app.utils.jwt import create_access_token, create_refresh_token, decode_token
from app.utils.passwords import hash_password, verify_password


class AuthService:
    """Business logic for authentication. Routes stay thin; this is where it lives."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(self, email: str, password: str) -> User:
        if await user_repo.get_user_by_email(self.db, email) is not None:
            raise EmailAlreadyRegistered(email)
        user = User(email=email, password_hash=hash_password(password))
        return await user_repo.create_user(self.db, user)

    async def authenticate(self, email: str, password: str) -> User:
        user = await user_repo.get_user_by_email(self.db, email)
        if (
            user is None
            or user.password_hash is None
            or not verify_password(password, user.password_hash)
        ):
            raise InvalidCredentials()
        return user

    async def login_with_google(self, code: str, client: httpx.AsyncClient) -> User:
        google_tokens = await google_oauth.exchange_code(client, code)
        userinfo = await google_oauth.fetch_userinfo(client, google_tokens["access_token"])
        google_sub = userinfo["sub"]
        email = userinfo["email"]

        user = await user_repo.get_user_by_google_sub(self.db, google_sub)
        if user is not None:
            return user

        # Link an existing local account by email, or create a fresh one.
        user = await user_repo.get_user_by_email(self.db, email)
        if user is None:
            user = User(email=email, google_sub=google_sub)
            return await user_repo.create_user(self.db, user)
        user.google_sub = google_sub
        return await user_repo.update_user(self.db, user)

    async def refresh_tokens(self, refresh_token: str) -> User:
        try:
            payload = decode_token(refresh_token)
        except Exception as exc:
            raise InvalidToken() from exc
        if payload.get("type") != "refresh":
            raise InvalidToken()
        user = await user_repo.get_user_by_id(self.db, uuid.UUID(str(payload["sub"])))
        if user is None:
            raise InvalidToken()
        return user

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> None:
        if user.password_hash is None:
            raise PasswordNotSet()
        if not verify_password(current_password, user.password_hash):
            raise InvalidCredentials()
        user.password_hash = hash_password(new_password)
        await user_repo.update_user(self.db, user)

    def issue_tokens(self, user: User) -> TokenPair:
        subject = str(user.id)
        return TokenPair(
            access_token=create_access_token(subject),
            refresh_token=create_refresh_token(subject),
        )
