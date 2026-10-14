import asyncio
from typing import Any

import aio_pika
import orjson
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractRobustConnection

from app.conf.config import get_settings
from app.logger.logger_config import logger
from app.services import llm_client


async def publish(
    channel: AbstractChannel, message: AbstractIncomingMessage, body: bytes
) -> None:
    """Send one reply body back on the request's reply_to, tagged with its id."""
    if message.reply_to is not None:
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=body,
                correlation_id=message.correlation_id,
                content_type="application/json",
            ),
            routing_key=message.reply_to,
        )


async def handle_stream_reply(
    channel: AbstractChannel, message: AbstractIncomingMessage, payload: dict[str, Any]
) -> None:
    """Stream reply deltas as many messages, ending with a `done` marker."""
    parts: list[str] = []
    try:
        async for delta in llm_client.stream_reply(
            system=payload.get("system", ""),
            history=payload.get("history", []),
            user=payload["user"],
            # TEMPORARY: history-policy experiment. Absent flag keeps caching on.
            cache=payload.get("cache", True),
        ):
            parts.append(delta)
            await publish(channel, message, orjson.dumps({"delta": delta}))
        await publish(channel, message, orjson.dumps({"done": True, "text": "".join(parts)}))
        logger.info(f"LLM stream reply: {len(parts)} deltas, {sum(map(len, parts))} chars")
    except Exception as exc:
        logger.exception("LLM stream reply failed")
        await publish(channel, message, orjson.dumps({"error": str(exc)}))


async def handle_stream_reply_2(
    channel: AbstractChannel, message: AbstractIncomingMessage, payload: dict[str, Any]
) -> None:
    """Stream handler for the TOKEN-BUDGET experiment set. TEMPORARY."""
    parts: list[str] = []
    try:
        async for delta in llm_client.stream_reply_2(
            system=payload.get("system", ""),
            history=payload.get("history", []),
            user=payload["user"],
            policy=payload.get("policy", ""),
        ):
            parts.append(delta)
            await publish(channel, message, orjson.dumps({"delta": delta}))
        await publish(channel, message, orjson.dumps({"done": True, "text": "".join(parts)}))
        logger.info(f"LLM stream reply 2: {len(parts)} deltas, {sum(map(len, parts))} chars")
    except Exception as exc:
        logger.exception("LLM stream reply 2 failed")
        await publish(channel, message, orjson.dumps({"error": str(exc)}))


async def handle_corrections(
    channel: AbstractChannel, message: AbstractIncomingMessage, payload: dict[str, Any]
) -> None:
    """Run the corrections-only pass and reply once."""
    try:
        result = await llm_client.detect_corrections(
            system=payload.get("system", ""),
            history=payload.get("history", []),
            user=payload["user"],
        )
        body = orjson.dumps(result)
        logger.info(f"LLM corrections: {len(result['corrections'])} found")
    except Exception as exc:
        logger.exception("LLM corrections pass failed")
        body = orjson.dumps({"error": str(exc)})
    await publish(channel, message, body)


async def connect_with_retry(
    url: str, attempts: int = 30, delay: float = 2.0
) -> AbstractRobustConnection:
    for attempt in range(1, attempts + 1):
        try:
            return await aio_pika.connect_robust(url)
        except Exception as exc:  # broker may not be up yet
            logger.warning(f"RabbitMQ not ready (attempt {attempt}/{attempts}): {exc}")
            await asyncio.sleep(delay)
    raise RuntimeError("Could not connect to RabbitMQ")


async def handle_structured_turn(
    channel: AbstractChannel, message: AbstractIncomingMessage, payload: dict[str, Any]
) -> None:
    """v1 walkie-talkie: one structured reply (spoken_reply + corrections)."""
    try:
        reply = await llm_client.generate_reply(
            system=payload.get("system", ""),
            history=payload.get("history", []),
            user=payload["user"],
        )
        body = orjson.dumps(reply)
        logger.info(
            f"LLM reply: {len(reply['spoken_reply'])} chars, "
            f"{len(reply['corrections'])} corrections"
        )
    except Exception as exc:
        logger.exception("LLM call failed")
        body = orjson.dumps({"error": str(exc)})
    await publish(channel, message, body)


async def process_message(
    channel: AbstractChannel, message: AbstractIncomingMessage
) -> None:
    payload: dict[str, Any] = orjson.loads(message.body)
    mode = payload.get("mode")
    if mode == "stream_reply":
        await handle_stream_reply(channel, message, payload)
    elif mode == "stream_reply_2":          # TEMPORARY: token-budget experiment
        await handle_stream_reply_2(channel, message, payload)
    elif mode == "corrections":
        await handle_corrections(channel, message, payload)
    else:
        await handle_structured_turn(channel, message, payload)


async def run_worker() -> None:
    settings = get_settings()

    connection = await connect_with_retry(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=settings.prefetch_count)
    queue = await channel.declare_queue(settings.llm_queue, durable=False)
    logger.info(f"LLM worker ready, consuming '{settings.llm_queue}' (model={settings.llm_model})")

    async with queue.iterator() as iterator:
        async for message in iterator:
            async with message.process(requeue=False):
                await process_message(channel, message)
