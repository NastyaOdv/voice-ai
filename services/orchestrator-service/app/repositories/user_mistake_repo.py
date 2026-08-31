import uuid

from sqlalchemy import ColumnElement, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserMistake


async def list_mistakes_by_user(
    db: AsyncSession, user_id: uuid.UUID, order_by: list[ColumnElement]
) -> list[UserMistake]:
    """List a user's mistakes, ordered by the given expressions (if any).

    `order_by` is a list of validated SQLAlchemy expressions built by the caller from
    an allowlist (never raw client strings). Empty list -> no ORDER BY.
    """
    stmt = select(UserMistake).where(UserMistake.user_id == user_id)
    if order_by:
        stmt = stmt.order_by(*order_by)
    result = await db.scalars(stmt)
    return list(result.all())


async def create_user_mistakes(
    db: AsyncSession, mistakes: list[UserMistake]
) -> list[UserMistake]:
    if not mistakes:
        return []
    try:
        db.add_all(mistakes)
        await db.flush()
        for mistake in mistakes:
            await db.refresh(mistake)
        await db.commit()
        return mistakes
    except SQLAlchemyError as e:
        await db.rollback()
        raise e
