from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GrammarTopic


async def list_topics(db: AsyncSession) -> list[GrammarTopic]:
    result = await db.scalars(select(GrammarTopic).order_by(GrammarTopic.id))
    return list(result.all())
