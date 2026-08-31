import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.async_session_manager import Base


class Correction(Base):
    """A grammar correction attached to a user turn (text only, never spoken)."""

    __tablename__ = "or_corrections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    turn_id = Column(UUID(as_uuid=True), ForeignKey("or_turns.id"), nullable=False)
    topic = Column(String, nullable=False, server_default="")
    you_said = Column(String, nullable=False)
    better = Column(String, nullable=False)
    note = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
