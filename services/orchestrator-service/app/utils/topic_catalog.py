import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import grammar_topic_repo

# In-process cache of the (static) grammar-topic catalog: the names passed to the LLM
# and a normalized name -> id map used to resolve each correction's topic to a row.
_topic_names: list[str] | None = None
_topic_index: dict[str, int] | None = None


def normalize_topic(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().casefold()


async def load_topic_catalog(db: AsyncSession) -> tuple[list[str], dict[str, int]]:
    global _topic_names, _topic_index
    if _topic_names is None or _topic_index is None:
        topics = await grammar_topic_repo.list_topics(db)
        names = [t.name for t in topics]
        index: dict[str, int] = {}
        for topic in topics:
            index.setdefault(normalize_topic(topic.name), topic.id)
        _topic_names, _topic_index = names, index
    return _topic_names, _topic_index
