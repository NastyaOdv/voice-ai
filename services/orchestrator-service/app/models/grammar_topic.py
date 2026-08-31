from sqlalchemy import Column, Integer, String

from app.db.async_session_manager import Base


class GrammarTopic(Base):
    """Static catalog of CEFR grammar topics (seeded from app.data.grammar_topics).

    The list of `name`s is passed to the LLM so it classifies each mistake into one of
    these canonical topics; `UserMistake.topic_id` points back here. Integer PK (not
    UUID) because rows are a fixed, seeded reference set.
    """

    __tablename__ = "or_grammar_topics"

    id = Column(Integer, primary_key=True)
    level = Column(String(8), nullable=False)  # CEFR: A1, A2, B1, B2
    category = Column(String, nullable=False)
    name = Column(String, nullable=False, index=True)
