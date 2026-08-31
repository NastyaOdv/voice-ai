import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserMistake
from app.repositories import user_mistake_repo
from app.utils.ordering import parse_order_by
from app.utils.topic_catalog import load_topic_catalog, normalize_topic

# Topic used when the LLM does not classify a mistake — so `topic` is never empty.
UNCATEGORIZED_TOPIC = "Uncategorized"


class MistakeService:
    """Owns the per-user grammar-mistake profile: logging turns' mistakes and reading."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log_mistakes(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        turn_id: uuid.UUID,
        corrections: list[dict],
    ) -> list[UserMistake]:
        """Persist one turn's grammar mistakes against the user, one row per correction.

        Resolves each LLM topic label to a catalog row so mistakes can be grouped by a
        canonical topic; unclassified mistakes fall back to `Uncategorized`.
        """
        _, topic_index = await load_topic_catalog(self.db)
        return await user_mistake_repo.create_user_mistakes(
            self.db,
            [
                UserMistake(
                    user_id=user_id,
                    session_id=session_id,
                    turn_id=turn_id,
                    topic=item.get("topic") or UNCATEGORIZED_TOPIC,
                    topic_id=topic_index.get(normalize_topic(item.get("topic", ""))),
                    example=item["you_said"],
                    better=item["better"],
                    note=item["note"],
                )
                for item in corrections
            ],
        )

    async def list_mistakes(
        self, user_id: uuid.UUID, order_by: list[str] | None = None
    ) -> list[UserMistake]:
        order_expressions = parse_order_by(UserMistake, order_by or [])
        return await user_mistake_repo.list_mistakes_by_user(
            self.db, user_id, order_expressions
        )
