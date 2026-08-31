from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MistakeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    example: str
    better: str
    note: str
    created_at: datetime


class TopicMistakes(BaseModel):
    """A learner's mistakes for one grammar topic, with the total count."""

    topic: str
    count: int
    mistakes: list[MistakeRead]
