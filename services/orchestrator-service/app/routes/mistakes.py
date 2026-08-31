import uuid

from fastapi import APIRouter, Depends, Query

from app.schemas import MistakeRead, TopicMistakes
from app.services.mistake_service import MistakeService
from app.utils.dependencies import get_current_user_id, get_mistake_service

router = APIRouter(prefix="/mistakes", tags=["mistakes"])


@router.get("", response_model=list[TopicMistakes])
async def list_mistakes(
    order_by: list[str] = Query(default=["topic"]),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: MistakeService = Depends(get_mistake_service),
) -> list[TopicMistakes]:
    rows = await service.list_mistakes(user_id, order_by)
    groups: dict[str, list] = {}
    for row in rows:  # first-seen order preserved -> groups follow the query order
        groups.setdefault(row.topic, []).append(row)
    return [
        TopicMistakes(
            topic=topic,
            count=len(items),
            mistakes=[MistakeRead.model_validate(m) for m in items],
        )
        for topic, items in groups.items()
    ]
