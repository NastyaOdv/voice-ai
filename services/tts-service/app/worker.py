"""RabbitMQ worker: consume the tts.rpc queue, synthesize speech, reply to reply_to.

Synthesis is CPU-bound and blocking, so it runs in a thread (asyncio.to_thread) to
keep the event loop responsive. prefetch=1 processes one request at a time.

Contract:
  { "text": "..." }  ->  { "audio_b64": "<base64 WAV>" }
"""
import asyncio
import base64
from typing import Any

import aio_pika
import orjson
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractRobustConnection

from app.conf.config import get_settings
from app.logger.logger_config import logger
from app.services import synthesizer


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


async def process_message(
    channel: AbstractChannel, message: AbstractIncomingMessage
) -> None:
    payload: dict[str, Any] = orjson.loads(message.body)
    text: str = payload["text"]
    try:
        wav = await asyncio.to_thread(synthesizer.synthesize, text)
        body = orjson.dumps({"audio_b64": base64.b64encode(wav).decode()})
        logger.info(f"Synthesized {len(text)} chars -> {len(wav)} bytes WAV")
    except Exception as exc:
        logger.exception("Synthesis failed")
        body = orjson.dumps({"error": str(exc)})

    if message.reply_to is not None:
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=body,
                correlation_id=message.correlation_id,
                content_type="application/json",
            ),
            routing_key=message.reply_to,
        )


async def run_worker() -> None:
    settings = get_settings()

    # Warm up the voice before consuming so the first request is not slow.
    synthesizer.get_voice()

    connection = await connect_with_retry(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=settings.prefetch_count)
    queue = await channel.declare_queue(settings.tts_queue, durable=False)
    logger.info(f"TTS worker ready, consuming '{settings.tts_queue}'")

    async with queue.iterator() as iterator:
        async for message in iterator:
            async with message.process(requeue=False):
                await process_message(channel, message)
