import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    """Payload for creating a user."""

    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str | None = None


class UserRead(BaseModel):
    """User representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str | None
    created_at: datetime
    updated_at: datetime
