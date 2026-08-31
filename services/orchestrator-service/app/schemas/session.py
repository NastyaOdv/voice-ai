import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.turn import TurnRead


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    summary: str | None
    created_at: datetime


class SessionDetail(SessionRead):
    turns: list[TurnRead]
