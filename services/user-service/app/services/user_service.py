import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.repositories import user_repo


class UserService:
    """Business logic for user profiles. Routes stay thin; this is where it lives.

    Currently minimal — grows as profile CRUD lands.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await user_repo.get_user_by_id(self.db, user_id)
