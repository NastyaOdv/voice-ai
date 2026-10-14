"""LLM client for the English tutor, talking to the LiteLLM gateway.

Every call goes to the LiteLLM proxy, never to a provider directly: `llm_model` is a
LiteLLM alias and which vendor serves it is decided there, so swapping model or provider
never touches this file.

Returns a STRUCTURED response so the two parts never mix: `spoken_reply` (voiced by
TTS) and `corrections` (grammar notes, text-only). We use the SDK's `messages.parse`
with a Pydantic schema so the output is validated against that shape.

Thinking is disabled: this is a short, well-specified structured task, so we keep
latency and cost down and guarantee the JSON fits in `max_tokens`.

NOTE: `cache_control` and `thinking` below are Anthropic-format fields. A provider that
does not implement them (e.g. Gemini) ignores them silently and every call is billed
uncached — the usage log then shows `cache_read=0`. Check what the alias resolves to
before reading the cache figures.
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

REPLY_SYSTEM_PROMPT = "You are a helpful assistant. Reply with a short spoken line."
CORRECTIONS_SYSTEM_PROMPT = (
    "List the grammar mistakes in the user's latest message as objects with 'topic', "
    "'you_said', 'better' and 'note'. Return an empty list if there are none."
)

# Said when the model declines to answer, so the pipeline never breaks.
REFUSAL_REPLY = "Sorry, I couldn't process that. Could you say it again?"


@lru_cache
def get_client() -> AsyncAnthropic:
    # The SDK is used purely as a client for LiteLLM's Anthropic-compatible /v1/messages
    # endpoint, authenticated with a LiteLLM virtual key. Provider keys live in LiteLLM,
    # which routes `llm_model` (a public alias) to the actual model — so switching model
    # or provider is a config change there, not a code change here.
    settings = get_settings()
    return AsyncAnthropic(base_url=settings.llm_base_url, api_key=settings.llm_api_key)


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

    # Context size before the call (~4 chars per token) — use it to calibrate the
    # history window: how deep the context is and what each part costs.
    logger.info(
        "[structured] context: turns=%s sys_tok~%s hist_tok~%s user_tok~%s",
        len(history) // 2,
        len(system_text) // 4,
        sum(len(m.get("content", "")) for m in history) // 4,
        len(user) // 4,
    )

    response = await get_client().messages.parse(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        thinking={"type": "disabled"},
        system=cached_system(system_text),
        messages=with_history_cache(conversation),  # type: ignore[arg-type]
        output_format=TutorReply,
    )

    usage = response.usage
    # input_tokens counts only what was NOT served from cache, so the real input is
    # input + cache_write + cache_read. A high cache_hit means the resent history is
    # being reused; a drop means a cold rebuild (e.g. Redis expired).
    cache_read = usage.cache_read_input_tokens or 0
    cache_write = usage.cache_creation_input_tokens or 0
    total_input = usage.input_tokens + cache_write + cache_read
    logger.info(
        "[structured] usage: input=%s cache_write=%s cache_read=%s output=%s "
        "total_input=%s cache_hit=%.0f%%",
        usage.input_tokens,
        cache_write,
        cache_read,
        usage.output_tokens,
        total_input,
        cache_read / total_input * 100 if total_input else 0,
    )

    if response.stop_reason == "refusal" or response.parsed_output is None:
        logger.warning("LLM declined or returned no structured output")
        return {"spoken_reply": REFUSAL_REPLY, "corrections": []}

    return response.parsed_output.model_dump()


async def stream_reply(
    system: str, history: list[dict[str, str]], user: str, cache: bool = True
) -> AsyncIterator[str]:
    """Stream ONLY the spoken reply as plain text deltas (E4 realtime path).

    No structured output here: the orchestrator segments these deltas into sentences and
    voices them as they complete, so the tutor starts speaking before the model finishes.

    `cache=False` sends the same request with no `cache_control` marker anywhere —
    TEMPORARY, for the history-policy experiment; the orchestrator sets it per policy.
    """
    settings = get_settings()
    system_text = system or REPLY_SYSTEM_PROMPT
    conversation = build_conversation(history, user)

    logger.info(
        "[stream] context: turns=%s sys_tok~%s hist_tok~%s user_tok~%s cache=%s",
        len(history) // 2,
        len(system_text) // 4,
        sum(len(m.get("content", "")) for m in history) // 4,
        len(user) // 4,
        "on" if cache else "off",
    )

    async with get_client().messages.stream(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        thinking={"type": "disabled"},
        system=cached_system(system_text) if cache else system_text,
        messages=(  # type: ignore[arg-type]
            with_history_cache(conversation) if cache else conversation
        ),
    ) as stream:
        async for text in stream.text_stream:
            yield text

        # Usage is only complete once the stream has finished.
        usage = (await stream.get_final_message()).usage
        cache_read = usage.cache_read_input_tokens or 0
        cache_write = usage.cache_creation_input_tokens or 0
        total_input = usage.input_tokens + cache_write + cache_read
        logger.info(
            "[stream] usage: input=%s cache_write=%s cache_read=%s output=%s "
            "total_input=%s cache_hit=%.0f%%",
            usage.input_tokens,
            cache_write,
            cache_read,
            usage.output_tokens,
            total_input,
            cache_read / total_input * 100 if total_input else 0,
        )


async def stream_reply_2(
    system: str, history: list[dict[str, str]], user: str, policy: str = ""
) -> AsyncIterator[str]:
    """Same stream as `stream_reply`, for the TOKEN-BUDGET experiment set.

    Split out so the two experiment sets land under different log tags and cannot be
    mixed up when the runs are compared. Caching is always on here: below the 4096
    minimum `cache_control` is ignored and costs nothing, and none of the token-budget
    windows moves its prefix per turn. TEMPORARY, delete with the experiment.
    """
    settings = get_settings()
    system_text = system or REPLY_SYSTEM_PROMPT
    conversation = build_conversation(history, user)

    logger.info(
        "[stream2] context: policy=%s turns=%s sys_tok~%s hist_tok~%s user_tok~%s",
        policy or "?",
        len(history) // 2,
        len(system_text) // 4,
        sum(len(m.get("content", "")) for m in history) // 4,
        len(user) // 4,
    )

    async with get_client().messages.stream(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        thinking={"type": "disabled"},
        system=cached_system(system_text),
        messages=with_history_cache(conversation),  # type: ignore[arg-type]
    ) as stream:
        async for text in stream.text_stream:
            yield text

        usage = (await stream.get_final_message()).usage
        cache_read = usage.cache_read_input_tokens or 0
        cache_write = usage.cache_creation_input_tokens or 0
        total_input = usage.input_tokens + cache_write + cache_read
        logger.info(
            "[stream2] usage: policy=%s input=%s cache_write=%s cache_read=%s output=%s "
            "total_input=%s cache_hit=%.0f%%",
            policy or "?",
            usage.input_tokens,
            cache_write,
            cache_read,
            usage.output_tokens,
            total_input,
            cache_read / total_input * 100 if total_input else 0,
        )


async def detect_corrections(
    system: str, history: list[dict[str, str]], user: str
) -> dict[str, Any]:
    """Second pass: structured grammar corrections for the user's latest message."""
    settings = get_settings()
    system_text = system or CORRECTIONS_SYSTEM_PROMPT
    conversation = build_conversation(history, user)

    logger.info(
        "[corrections] context: turns=%s sys_tok~%s hist_tok~%s user_tok~%s",
        len(history) // 2,
        len(system_text) // 4,
        sum(len(m.get("content", "")) for m in history) // 4,
        len(user) // 4,
    )

    response = await get_client().messages.parse(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        thinking={"type": "disabled"},
        system=cached_system(system_text),
        messages=with_history_cache(conversation),  # type: ignore[arg-type]
        output_format=Corrections,
    )

    usage = response.usage
    cache_read = usage.cache_read_input_tokens or 0
    cache_write = usage.cache_creation_input_tokens or 0
    total_input = usage.input_tokens + cache_write + cache_read
    logger.info(
        "[corrections] usage: input=%s cache_write=%s cache_read=%s output=%s "
        "total_input=%s cache_hit=%.0f%%",
        usage.input_tokens,
        cache_write,
        cache_read,
        usage.output_tokens,
        total_input,
        cache_read / total_input * 100 if total_input else 0,
    )

    if response.stop_reason == "refusal" or response.parsed_output is None:
        logger.warning("Corrections pass declined or returned no structured output")
        return {"corrections": []}

    return response.parsed_output.model_dump()
