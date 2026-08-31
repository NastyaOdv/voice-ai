import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.async_session_manager import Base


class UserMistake(Base):
    """A grammar mistake logged directly against a user.

    Unlike `Correction` (which hangs off a turn), this table accumulates a per-user
    history of mistakes grouped by `topic`, so we can build an error profile across
    all of a learner's sessions. One row is created per correction the LLM produces.
    """

    __tablename__ = "or_user_mistakes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Owner — the auth user id (no cross-service FK, plain column).
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("or_sessions.id"), nullable=False)
    turn_id = Column(UUID(as_uuid=True), ForeignKey("or_turns.id"), nullable=False)
    topic = Column(String, nullable=False)  # raw topic label returned by the LLM
    # Link to the canonical catalog topic; nullable if the LLM's label matched nothing.
    topic_id = Column(Integer, ForeignKey("or_grammar_topics.id"), nullable=True)
    example = Column(String, nullable=False)  # what the learner actually said
    better = Column(String, nullable=False)
    note = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
