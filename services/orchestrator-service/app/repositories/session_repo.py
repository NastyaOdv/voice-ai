import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session


async def get_session_by_id(db: AsyncSession, session_id: uuid.UUID) -> Session | None:
    return await db.get(Session, session_id)


async def list_sessions_by_user(db: AsyncSession, user_id: uuid.UUID) -> list[Session]:
    result = await db.scalars(
        select(Session).where(Session.user_id == user_id).order_by(Session.created_at.desc())
    )
    return list(result.all())


async def create_session(db: AsyncSession, session_row: Session) -> Session:
    try:
        db.add(session_row)
        await db.flush()
        await db.refresh(session_row)
        await db.commit()
        return session_row
    except SQLAlchemyError as e:
        await db.rollback()
        raise e


async def update_session(db: AsyncSession, session_row: Session) -> Session:
    try:
        await db.flush()
        await db.refresh(session_row)
        await db.commit()
        return session_row
    except SQLAlchemyError as e:
        await db.rollback()
        raise e
