"""Worker routing + reply-protocol tests (T4.3). No real Anthropic calls."""
import orjson
import pytest

from app import worker
from app.services import llm_client


class FakeExchange:
    def __init__(self) -> None:
        self.published: list[bytes] = []

    async def publish(self, message, routing_key):  # noqa: ANN001
        self.published.append(message.body)


class FakeChannel:
    def __init__(self) -> None:
        self.default_exchange = FakeExchange()


class FakeMessage:
    def __init__(self, payload: dict) -> None:
        self.body = orjson.dumps(payload)
        self.reply_to = "reply.q"
        self.correlation_id = "corr-1"


def _bodies(channel: FakeChannel) -> list[dict]:
    return [orjson.loads(b) for b in channel.default_exchange.published]


async def test_stream_reply_mode_emits_deltas_then_done(monkeypatch):
    async def fake_stream(system, history, user):
        for token in ["Hello", " there", "."]:
            yield token

    monkeypatch.setattr(llm_client, "stream_reply", fake_stream)
    channel = FakeChannel()

    await worker.process_message(channel, FakeMessage({"mode": "stream_reply", "user": "hi"}))

    bodies = _bodies(channel)
    assert bodies[:3] == [{"delta": "Hello"}, {"delta": " there"}, {"delta": "."}]
    assert bodies[-1] == {"done": True, "text": "Hello there."}


async def test_stream_reply_mode_reports_errors_as_error_chunk(monkeypatch):
    async def boom(system, history, user):
        raise RuntimeError("upstream down")
        yield  # pragma: no cover — makes this an async generator

    monkeypatch.setattr(llm_client, "stream_reply", boom)
    channel = FakeChannel()

    await worker.process_message(channel, FakeMessage({"mode": "stream_reply", "user": "hi"}))

    assert _bodies(channel) == [{"error": "upstream down"}]


async def test_corrections_mode_replies_once_with_corrections(monkeypatch):
    async def fake_detect(system, history, user):
        return {"corrections": [{"topic": "Articles", "you_said": "a apple",
                                 "better": "an apple", "note": "use 'an'"}]}

    monkeypatch.setattr(llm_client, "detect_corrections", fake_detect)
    channel = FakeChannel()

    await worker.process_message(channel, FakeMessage({"mode": "corrections", "user": "a apple"}))

    bodies = _bodies(channel)
    assert len(bodies) == 1
    assert bodies[0]["corrections"][0]["better"] == "an apple"


async def test_no_mode_falls_back_to_structured_v1(monkeypatch):
    async def fake_generate(system, history, user):
        return {"spoken_reply": "Nice!", "corrections": []}

    monkeypatch.setattr(llm_client, "generate_reply", fake_generate)
    channel = FakeChannel()

    await worker.process_message(channel, FakeMessage({"user": "hi"}))

    assert _bodies(channel) == [{"spoken_reply": "Nice!", "corrections": []}]
