import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.correction import CorrectionRead


class TurnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    text: str
    language: str | None = None
    corrections: list[CorrectionRead] = []
    audio_url: str | None = None
    created_at: datetime


class TurnResult(BaseModel):
    """Response of submitting a user turn: the transcript, the spoken reply, notes."""

    turn_id: uuid.UUID
    transcript: str
    language: str | None
    spoken_reply: str
    corrections: list[CorrectionRead]
    audio_url: str
