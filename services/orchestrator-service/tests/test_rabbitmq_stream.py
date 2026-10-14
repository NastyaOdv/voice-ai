"""Tests for the streaming RPC broker (E1: `RpcClient.call_stream`).

These exercise the client's reply-routing logic (Future for `call`, Queue for
`call_stream`) without a real RabbitMQ: the channel is mocked and replies are injected
by calling `on_response` with fake messages, exactly as the callback queue would.
"""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import orjson
import pytest

from app.utils.exceptions import PipelineError
from app.utils.rabbitmq import RpcClient

FIXED_CORR = str(uuid.UUID(int=1))


def make_connected_client(monkeypatch) -> RpcClient:
    """An RpcClient with a mocked channel/callback queue and a deterministic corr-id."""
    client = RpcClient("amqp://test")
    client.channel = SimpleNamespace(
        default_exchange=SimpleNamespace(publish=AsyncMock())
    )
    client.callback_queue = SimpleNamespace(name="cbq")
    monkeypatch.setattr(
        "app.utils.rabbitmq.uuid.uuid4", lambda: uuid.UUID(int=1)
    )
    return client


def reply(correlation_id: str, body: dict) -> SimpleNamespace:
    """A stand-in for an aio_pika incoming JSON message."""
    return SimpleNamespace(
        correlation_id=correlation_id,
        body=orjson.dumps(body),
        content_type="application/json",
        headers={},
    )


def binary_reply(
    correlation_id: str, audio: bytes, meta: dict | None = None
) -> SimpleNamespace:
    """A stand-in for a binary reply: raw bytes in the body, JSON meta in a header."""
    return SimpleNamespace(
        correlation_id=correlation_id,
        body=audio,
        content_type="application/octet-stream",
        headers={"meta": orjson.dumps(meta).decode()} if meta else {},
    )


async def _wait_registered(client: RpcClient, corr: str) -> None:
    for _ in range(100):
        if corr in client.streams:
            return
        await asyncio.sleep(0)
    raise AssertionError("stream was never registered")


async def test_call_stream_yields_chunks_until_done(monkeypatch):
    client = make_connected_client(monkeypatch)
    collected: list[dict] = []

    async def collect() -> None:
        async for chunk in client.call_stream("llm.rpc", {"user": "hi"}):
            collected.append(chunk)

    task = asyncio.create_task(collect())
    await _wait_registered(client, FIXED_CORR)

    for delta in ("Sure,", " that's", " it."):
        await client.on_response(reply(FIXED_CORR, {"delta": delta}))
    await client.on_response(reply(FIXED_CORR, {"done": True}))

    await asyncio.wait_for(task, timeout=1)
    assert collected == [{"delta": "Sure,"}, {"delta": " that's"}, {"delta": " it."}]
    assert FIXED_CORR not in client.streams  # cleaned up after the stream ends

    # request went to the right queue, carrying our correlation id + reply_to
    published = client.channel.default_exchange.publish.call_args
    assert published.kwargs["routing_key"] == "llm.rpc"
    assert published.args[0].correlation_id == FIXED_CORR
    assert published.args[0].reply_to == "cbq"


async def test_call_stream_raises_on_error_chunk(monkeypatch):
    client = make_connected_client(monkeypatch)

    async def collect() -> None:
        async for _ in client.call_stream("llm.rpc", {"user": "hi"}):
            pass

    task = asyncio.create_task(collect())
    await _wait_registered(client, FIXED_CORR)
    await client.on_response(reply(FIXED_CORR, {"error": "worker exploded"}))

    with pytest.raises(PipelineError, match="worker exploded"):
        await asyncio.wait_for(task, timeout=1)
    assert FIXED_CORR not in client.streams


async def test_call_stream_times_out_and_cleans_up(monkeypatch):
    client = make_connected_client(monkeypatch)
    with pytest.raises(asyncio.TimeoutError):
        async for _ in client.call_stream("llm.rpc", {}, timeout=0.05):
            pass
    assert client.streams == {}


async def test_call_still_returns_single_reply(monkeypatch):
    """Regression: the classic request/reply `call` keeps working alongside streaming."""
    client = make_connected_client(monkeypatch)
    task = asyncio.create_task(client.call("stt.rpc", {"x": 1}))
    for _ in range(100):
        if FIXED_CORR in client.futures:
            break
        await asyncio.sleep(0)
    await client.on_response(reply(FIXED_CORR, {"text": "hello"}))
    assert await asyncio.wait_for(task, timeout=1) == {"text": "hello"}


async def test_call_sends_binary_body_and_decodes_binary_reply(monkeypatch):
    """`audio=` publishes raw bytes + a JSON `meta` header (no base64), and a binary
    reply decodes back to a dict carrying the raw bytes under `audio`."""
    client = make_connected_client(monkeypatch)
    task = asyncio.create_task(
        client.call("stt.rpc", {"lang": "en"}, audio=b"\x00\x01\x02\xff")
    )
    for _ in range(100):
        if FIXED_CORR in client.futures:
            break
        await asyncio.sleep(0)

    # request: raw bytes in the body, JSON metadata in the `meta` header
    published = client.channel.default_exchange.publish.call_args
    message = published.args[0]
    assert message.body == b"\x00\x01\x02\xff"
    assert message.content_type == "application/octet-stream"
    assert orjson.loads(message.headers["meta"]) == {"lang": "en"}

    # reply: raw WAV bytes come back as {"audio": b"..."}
    await client.on_response(binary_reply(FIXED_CORR, b"WAVE-bytes"))
    assert await asyncio.wait_for(task, timeout=1) == {"audio": b"WAVE-bytes"}
