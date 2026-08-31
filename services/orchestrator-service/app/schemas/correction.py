import uuid

from pydantic import BaseModel, ConfigDict


class CorrectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic: str
    you_said: str
    better: str
    note: str
