import uuid

from sqlalchemy import Column, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID

from app.db.async_session_manager import Base


class Session(Base):
    """A practice conversation session with the voice tutor."""

    __tablename__ = "or_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Owner of the session — the auth user id from the token (no cross-service FK).
    user_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(
        String(20), nullable=False, default="active", server_default=text("'active'")
    )
    summary = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    closed_at = Column(DateTime(timezone=True), nullable=True)
