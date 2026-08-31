import uuid

from sqlalchemy import Boolean, Column, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID

from app.db.async_session_manager import Base


class User(Base):
    """An identity record: a login that is either local (password) or Google-linked."""

    __tablename__ = "au_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, unique=True)
    # Null for Google-only accounts; set for local email/password accounts.
    password_hash = Column(String(255), nullable=True)
    # Google subject id (the stable user identifier from Google); null for local-only.
    google_sub = Column(String(255), nullable=True, unique=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
