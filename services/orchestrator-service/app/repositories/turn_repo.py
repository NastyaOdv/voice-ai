import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Turn


async def list_turns_by_session(db: AsyncSession, session_id: uuid.UUID) -> list[Turn]:
    result = await db.scalars(
        select(Turn).where(Turn.session_id == session_id).order_by(Turn.created_at.asc())
    )
    return list(result.all())


async def create_turn(db: AsyncSession, turn: Turn) -> Turn:
    try:
        db.add(turn)
        await db.flush()
        await db.refresh(turn)
        await db.commit()
        return turn
    except SQLAlchemyError as e:
        await db.rollback()
        raise e
