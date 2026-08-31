import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Correction


async def list_corrections_by_turns(
    db: AsyncSession, turn_ids: list[uuid.UUID]
) -> list[Correction]:
    """Fetch corrections for many turns in one query (avoids an N+1 over turns)."""
    if not turn_ids:
        return []
    result = await db.scalars(
        select(Correction).where(Correction.turn_id.in_(turn_ids))
    )
    return list(result.all())


async def create_corrections(db: AsyncSession, corrections: list[Correction]) -> list[Correction]:
    if not corrections:
        return []
    try:
        db.add_all(corrections)
        await db.flush()
        for correction in corrections:
            await db.refresh(correction)
        await db.commit()
        return corrections
    except SQLAlchemyError as e:
        await db.rollback()
        raise e
