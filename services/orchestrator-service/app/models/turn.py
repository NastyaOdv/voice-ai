import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.async_session_manager import Base


class Turn(Base):
    """A single utterance in a session: the user's speech or the assistant's reply."""

    __tablename__ = "or_turns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("or_sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)  # "user" | "assistant"
    text = Column(String, nullable=False)
    # Language detected by STT (user turns only), e.g. "en", "ru".
    language = Column(String(8), nullable=True)
    # Path to the stored audio file (user speech or synthesized reply); may be null.
    audio_path = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
