"""Hot session context in Redis: the message array sent to the LLM each turn.

Postgres is the source of truth; Redis is a fast cache with a TTL so the orchestrator
does not rebuild the whole history from the DB on every user turn.
"""
import uuid

import orjson
from redis.asyncio import Redis

from app.conf.config import get_settings

Message = dict[str, str]


def messages_key(session_id: uuid.UUID) -> str:
    return f"session:{session_id}:messages"


async def get_messages(redis: Redis, session_id: uuid.UUID) -> list[Message]:
    raw = await redis.get(messages_key(session_id))
    if raw is None:
        return []
    loaded: list[Message] = orjson.loads(raw)
    return loaded


async def set_messages(
    redis: Redis, session_id: uuid.UUID, messages: list[Message]
) -> None:
    await redis.set(
        messages_key(session_id),
        orjson.dumps(messages),
        ex=get_settings().session_ttl_seconds,
    )


async def append_messages(
    redis: Redis, session_id: uuid.UUID, new_messages: list[Message]
) -> None:
    messages = await get_messages(redis, session_id)
    messages.extend(new_messages)
    await set_messages(redis, session_id, messages)


async def clear_messages(redis: Redis, session_id: uuid.UUID) -> None:
    await redis.delete(messages_key(session_id))
