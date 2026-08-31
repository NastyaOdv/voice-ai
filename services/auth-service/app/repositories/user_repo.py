import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email))


async def get_user_by_google_sub(db: AsyncSession, google_sub: str) -> User | None:
    return await db.scalar(select(User).where(User.google_sub == google_sub))


async def create_user(db: AsyncSession, user: User) -> User:
    try:
        db.add(user)
        await db.flush()
        await db.refresh(user)
        await db.commit()
        return user
    except SQLAlchemyError as e:
        await db.rollback()
        raise e


async def update_user(db: AsyncSession, user: User) -> User:
    try:
        await db.flush()
        await db.refresh(user)
        await db.commit()
        return user
    except SQLAlchemyError as e:
        await db.rollback()
        raise e
