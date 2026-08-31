"""RabbitMQ RPC client (aio-pika).

Two reply patterns share one callback queue, correlated by `correlation_id`:

- `call` — classic request/reply ("walkie-talkie", Level 1): one request, one reply,
  delivered through an `asyncio.Future`.
- `call_stream` — streaming (Level 2): one request, many partial replies, then a
  `{"done": true}` marker. Chunks flow through an `asyncio.Queue` and are yielded as an
  async generator, so the orchestrator can act on LLM text as it arrives (feed finished
  sentences to TTS before the model has finished writing).
"""
import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import aio_pika
import orjson
from aio_pika.abc import (
    AbstractChannel,
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
)

from app.logger.logger_config import logger
from app.utils.exceptions import PipelineError

# Worker queue names (the STT/LLM/TTS services consume these).
STT_QUEUE = "stt.rpc"
LLM_QUEUE = "llm.rpc"
TTS_QUEUE = "tts.rpc"


class RpcClient:
    def __init__(self, amqp_url: str) -> None:
        self.amqp_url = amqp_url
        self.connection: AbstractRobustConnection | None = None
        self.channel: AbstractChannel | None = None
        self.callback_queue: AbstractQueue | None = None
        self.futures: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self.streams: dict[str, asyncio.Queue[dict[str, Any]]] = {}

    async def connect(self, attempts: int = 30, delay: float = 2.0) -> None:
        for attempt in range(1, attempts + 1):
            try:
                self.connection = await aio_pika.connect_robust(self.amqp_url)
                break
            except Exception as exc:  # broker may not accept connections yet
                logger.warning(
                    f"RabbitMQ not ready (attempt {attempt}/{attempts}): {exc}"
                )
                await asyncio.sleep(delay)
        else:
            raise RuntimeError("Could not connect to RabbitMQ")

        self.channel = await self.connection.channel()
        self.callback_queue = await self.channel.declare_queue(exclusive=True)
        await self.callback_queue.consume(self.on_response, no_ack=True)
        logger.info("RabbitMQ RPC client connected")

    async def on_response(self, message: AbstractIncomingMessage) -> None:
        if message.correlation_id is None:
            logger.warning("RPC response without correlation_id, dropping")
            return
        body = orjson.loads(message.body)

        # Streaming reply: push the chunk to the waiting generator (may be many).
        stream = self.streams.get(message.correlation_id)
        if stream is not None:
            stream.put_nowait(body)
            return

        # Single reply: resolve the one-shot future.
        future = self.futures.pop(message.correlation_id, None)
        if future is not None:
            future.set_result(body)

    async def _publish(
        self, routing_key: str, payload: dict[str, Any], correlation_id: str
    ) -> None:
        assert self.channel is not None and self.callback_queue is not None
        await self.channel.default_exchange.publish(
            aio_pika.Message(
                body=orjson.dumps(payload),
                content_type="application/json",
                correlation_id=correlation_id,
                reply_to=self.callback_queue.name,
            ),
            routing_key=routing_key,
        )

    async def call(
        self, routing_key: str, payload: dict[str, Any], timeout: float = 60.0
    ) -> dict[str, Any]:
        if self.channel is None or self.callback_queue is None:
            raise RuntimeError("RpcClient is not connected")

        correlation_id = str(uuid.uuid4())
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self.futures[correlation_id] = future
        try:
            await self._publish(routing_key, payload, correlation_id)
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self.futures.pop(correlation_id, None)

    async def call_stream(
        self, routing_key: str, payload: dict[str, Any], timeout: float = 60.0
    ) -> AsyncIterator[dict[str, Any]]:
        """Publish one request and yield partial replies until a `done` marker.

        `timeout` bounds the wait for *each* chunk (not the whole stream), so a worker
        that keeps producing keeps the generator alive. A chunk carrying `error` aborts
        the stream with `PipelineError`.
        """
        if self.channel is None or self.callback_queue is None:
            raise RuntimeError("RpcClient is not connected")

        correlation_id = str(uuid.uuid4())
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.streams[correlation_id] = queue
        try:
            await self._publish(routing_key, payload, correlation_id)
            while True:
                chunk = await asyncio.wait_for(queue.get(), timeout=timeout)
                if chunk.get("done"):
                    break
                if "error" in chunk:
                    raise PipelineError(str(chunk["error"]))
                yield chunk
        finally:
            self.streams.pop(correlation_id, None)

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
            logger.info("RabbitMQ RPC client closed")
