"""Anthropic Claude client for the English tutor.

Returns a STRUCTURED response so the two parts never mix: `spoken_reply` (voiced by
TTS) and `corrections` (grammar notes, text-only). We use the SDK's `messages.parse`
with a Pydantic schema so the output is validated against that shape.

Thinking is disabled: this is a short, well-specified structured task, so we keep
latency and cost down and guarantee the JSON fits in `max_tokens`.
"""
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from anthropic import AsyncAnthropic

from app.conf.config import get_settings
from app.logger.logger_config import logger
from app.models import Corrections, TutorReply

# Fallback system prompt if the orchestrator ever omits one from the context.
FALLBACK_SYSTEM_PROMPT = (
    "You are a friendly spoken-English tutor. Keep a natural spoken conversation and "
    "point out only GRAMMAR mistakes, each classified by a short grammar 'topic'."
)

# Fallback prompts for the split realtime pipeline (E4). The orchestrator normally
# supplies tuned prompts; these keep the worker safe if it ever omits one.
REPLY_SYSTEM_PROMPT = (
    "You are a friendly spoken-English tutor on a live voice call. Reply with a single "
    "natural spoken line that continues the conversation. Do NOT mention grammar "
    "mistakes or corrections. Do not include internal or system XML tags in your reply."
)
CORRECTIONS_SYSTEM_PROMPT = (
    "You review a language learner's latest message and list only their GRAMMAR "
    "mistakes, each with a short 'topic', what they said, a better version, and a short "
    "note. Return an empty list if there are none."
)

# Said when the model declines to answer, so the pipeline never breaks.
REFUSAL_REPLY = "Sorry, I couldn't process that. Could you say it again?"


@lru_cache
def get_client() -> AsyncAnthropic:
    # Reads ANTHROPIC_API_KEY from the environment.
    return AsyncAnthropic()


def build_conversation(
    history: list[dict[str, str]], user: str
) -> list[dict[str, str]]:
    """Assemble the Anthropic `messages` list from raw history + the new user turn.

    The orchestrator sends domain content; here we do the vendor-shape assembly and
    light validation: keep only well-formed user/assistant turns, then append the new
    user message so the conversation always ends with `user` (what the API expects).
    """
    conversation = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    conversation.append({"role": "user", "content": user})
    return conversation


def cached_system(system: str) -> list[dict[str, Any]]:
    """System prompt as a single cached block.

    The tutor instructions plus the grammar-topic catalog are large and identical on
    every turn, so we mark them with `cache_control` to read them from cache instead
    of paying full input cost each call.
    """
    return [
        {
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def with_history_cache(
    conversation: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Put a cache breakpoint on the last turn so the (resent) history is reused.

    The orchestrator resends the whole conversation every call; caching up to the last
    turn makes each new turn a prefix cache-hit for everything that came before it.
    """
    if not conversation:
        return list(conversation)
    prefix = [dict(m) for m in conversation[:-1]]
    last = conversation[-1]
    # The API rejects cache_control on an empty text block — leave such a turn uncached.
    if not last["content"]:
        return [*prefix, dict(last)]
    cached_last = {
        "role": last["role"],
        "content": [
            {
                "type": "text",
                "text": last["content"],
                "cache_control": {"type": "ephemeral"},
            }
        ],
    }
    return [*prefix, cached_last]


async def generate_reply(
    system: str, history: list[dict[str, str]], user: str
) -> dict[str, Any]:
    settings = get_settings()
    system_text = system or FALLBACK_SYSTEM_PROMPT
    conversation = build_conversation(history, user)

    response = await get_client().messages.parse(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        thinking={"type": "disabled"},
        system=cached_system(system_text),
        messages=with_history_cache(conversation),  # type: ignore[arg-type]
        output_format=TutorReply,
    )

    usage = response.usage
    logger.info(
        "LLM usage: input=%s cache_write=%s cache_read=%s output=%s",
        usage.input_tokens,
        usage.cache_creation_input_tokens,
        usage.cache_read_input_tokens,
        usage.output_tokens,
    )

    if response.stop_reason == "refusal" or response.parsed_output is None:
        logger.warning("LLM declined or returned no structured output")
        return {"spoken_reply": REFUSAL_REPLY, "corrections": []}

    return response.parsed_output.model_dump()


async def stream_reply(
    system: str, history: list[dict[str, str]], user: str
) -> AsyncIterator[str]:
    """Stream ONLY the spoken reply as plain text deltas (E4 realtime path).

    No structured output here: the orchestrator segments these deltas into sentences and
    voices them as they complete, so the tutor starts speaking before the model finishes.
    """
    settings = get_settings()
    system_text = system or REPLY_SYSTEM_PROMPT
    conversation = build_conversation(history, user)

    async with get_client().messages.stream(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        thinking={"type": "disabled"},
        system=cached_system(system_text),
        messages=with_history_cache(conversation),  # type: ignore[arg-type]
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def detect_corrections(
    system: str, history: list[dict[str, str]], user: str
) -> dict[str, Any]:
    """Second pass: structured grammar corrections for the user's latest message."""
    settings = get_settings()
    system_text = system or CORRECTIONS_SYSTEM_PROMPT
    conversation = build_conversation(history, user)

    response = await get_client().messages.parse(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        thinking={"type": "disabled"},
        system=cached_system(system_text),
        messages=with_history_cache(conversation),  # type: ignore[arg-type]
        output_format=Corrections,
    )

    if response.stop_reason == "refusal" or response.parsed_output is None:
        logger.warning("Corrections pass declined or returned no structured output")
        return {"corrections": []}

    return response.parsed_output.model_dump()
