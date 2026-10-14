import asyncio
import base64
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.conf.config import get_settings
from app.logger.logger_config import logger
from app.models import Correction, Session, Turn
from app.repositories import correction_repo, session_repo, turn_repo
from app.services.mistake_service import MistakeService
from app.utils import audio_storage, redis_cache
from app.utils.audio import concat_wavs
from app.utils.exceptions import NotSessionOwner, SessionClosed, SessionNotFound
from app.utils.history import trim_history, trim_history_tokens
from app.utils.rabbitmq import LLM_QUEUE, STT_QUEUE, TTS_QUEUE, RpcClient
from app.utils.text import SentenceAggregator
from app.utils.topic_catalog import load_topic_catalog

SYSTEM_PROMPT = (
    "You are a friendly spoken-English tutor. Keep a natural spoken conversation with "
    "the learner. Respond with JSON holding two fields: 'spoken_reply' — a natural line "
    "to say back to continue the conversation; and 'corrections' — a list of the "
    "learner's GRAMMAR mistakes only, each an object with 'topic', 'you_said', 'better' "
    "and 'note'. Never mention the corrections in spoken_reply."
)

# Realtime (E4) splits the one structured call into two: a streamed conversational reply
# and a separate corrections pass. Each gets its own focused system prompt.
REALTIME_REPLY_PROMPT = (
    "You are a friendly spoken-English tutor on a live voice call. Reply with one or two "
    "natural spoken sentences that continue the conversation, and ALWAYS end your reply "
    "with a question that invites the learner to keep talking. Do NOT mention grammar "
    "mistakes or corrections. Do not include internal or system XML tags in your reply."
)
CORRECTIONS_PROMPT = (
    "You review the learner's latest message and list only their GRAMMAR mistakes, each "
    "an object with 'topic', 'you_said', 'better' and 'note'. Return an empty list if "
    "there are none."
)

# Voiced back (and shown) when STT detects a non-English utterance: the tutor supports
# English only, so we skip the LLM entirely and just speak this line.
ENGLISH_ONLY_REPLY = (
    "I can only understand English right now. Could you say that again in English?"
)


# ---------------------------------------------------------------------------
# TEMPORARY — history-policy experiment for the cost write-up. Delete when done,
# together with the `cache` flag it puts in the llm.rpc payload.
#
# One policy per run: set REPLY_POLICY, rebuild orchestrator-api, drive a session,
# read the [stream] lines out of the llm-worker log. Only the spoken reply is under
# test — the corrections pass sends no history at all, so it is unaffected.
#
#   (max_pairs, keep_pairs, use_cache);  max_pairs = 0 means no trimming.
#   max_pairs = keep_pairs + 1 makes the window slide one pair per turn, which is
#   the "strict limit" shape; a wider gap makes it step.
# ---------------------------------------------------------------------------

REPLY_POLICIES: dict[str, tuple[int, int, bool]] = {
    "1_no_limit_no_cache": (0, 0, False),
    "2_no_limit_cache": (0, 0, True),
    "3_trim_20_no_cache": (21, 20, False),
    "4_trim_20_cache": (21, 20, True),
    "5_step_25_40": (40, 25, True),   # what the service shipped with
    "6_step_45_60": (60, 45, True),   # predicted to clear the 4096 cache minimum
}

REPLY_POLICY = "3_trim_20_no_cache"


def reply_policy(messages: list[dict[str, str]]) -> tuple[list[dict[str, str]], bool]:
    """History to send with the spoken reply, and whether to ask for prompt caching.

    `messages` is the full context including the system prompt at index 0, matching
    `SessionService.llm_history`.
    """
    max_pairs, keep_pairs, use_cache = REPLY_POLICIES[REPLY_POLICY]
    history = trim_history(messages[1:], max_pairs=max_pairs, keep_pairs=keep_pairs)
    return history, use_cache


# ---------------------------------------------------------------------------
# TEMPORARY — second experiment set, windows measured in TOKENS.
#
# The first set is expressed in turns, which turned out not to control anything: one
# exchange measured 100 tokens in one session and 222 in another, so the same setting
# landed above the 4096 cache minimum in one conversation and below it in the next.
# These windows are measured in the unit the price and the cache minimum use.
#
# Caching is on for all of them: below the minimum `cache_control` is ignored and costs
# nothing, and none of these windows moves its prefix per turn, so there is no case here
# where it would hurt. The first set already carries the cache-off control runs.
#
#   (keep_tokens, max_tokens, min_pairs, pin_pairs);  max_tokens = 0 means no trimming.
#   keep_tokens is chosen so that sys(82) + history + a short user turn stays clear of
#   4096 even right after a cut.
# ---------------------------------------------------------------------------

REPLY_POLICIES_2: dict[str, tuple[int, int, int, int]] = {
    "A_budget_floor": (4600, 6100, 8, 0),
    "B_budget_pinned": (4600, 6100, 8, 2),
    "D_no_trim": (0, 0, 0, 0),
}

REPLY_POLICY_2 = "A_budget_floor"

# Which experiment set runs: False = the turn-based set above, True = this one.
USE_POLICY_SET_2 = True


def reply_policy_2(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """History to send with the spoken reply under the token-budget experiment."""
    keep_tokens, max_tokens, min_pairs, pin_pairs = REPLY_POLICIES_2[REPLY_POLICY_2]
    return trim_history_tokens(
        messages[1:],
        keep_tokens=keep_tokens,
        max_tokens=max_tokens,
        min_pairs=min_pairs,
        pin_pairs=pin_pairs,
    )


def is_english(language: str | None) -> bool:
    """Whether an STT-detected language counts as English. Unknown (None) passes through
    so a failed detection never blocks a genuine English turn."""
    return language is None or language.split("-")[0].lower() == "en"


def turn_audio_url(session_id: uuid.UUID, turn_id: uuid.UUID) -> str:
    return f"/sessions/{session_id}/turns/{turn_id}/audio"


class SessionService:
    """Orchestrates the Audio -> STT -> LLM -> TTS pipeline for one user turn."""

    def __init__(self, db: AsyncSession, redis: Redis, broker: RpcClient) -> None:
        self.db = db
        self.redis = redis
        self.broker = broker

    async def build_system_prompt(self) -> str:
        """Base tutor prompt plus the catalog of grammar topics the LLM must pick from."""
        names, _ = await load_topic_catalog(self.db)
        if not names:
            return SYSTEM_PROMPT
        topics_block = "\n".join(f"- {name}" for name in names)
        return (
            f"{SYSTEM_PROMPT}\n\nThe 'topic' of each correction MUST be exactly one of "
            "the following grammar topics (copy the wording verbatim; choose the single "
            f"closest one):\n{topics_block}"
        )

    async def build_corrections_prompt(self) -> str:
        """Corrections-only prompt for the realtime second pass (topic catalog included)."""
        names, _ = await load_topic_catalog(self.db)
        if not names:
            return CORRECTIONS_PROMPT
        topics_block = "\n".join(f"- {name}" for name in names)
        return (
            f"{CORRECTIONS_PROMPT}\n\nThe 'topic' MUST be exactly one of the following "
            f"(copy the wording verbatim; choose the single closest one):\n{topics_block}"
        )

    def llm_history(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """The conversation turns to send the LLM: everything after the system prompt,
        bounded by the stepped window. The untrimmed context stays in Redis/Postgres."""
        settings = get_settings()
        return trim_history(
            messages[1:],
            max_pairs=settings.llm_history_max_pairs,
            keep_pairs=settings.llm_history_keep_pairs,
        )

    async def start_session(self, user_id: uuid.UUID) -> Session:
        session_row = Session(user_id=user_id, status="active")
        session_row = await session_repo.create_session(self.db, session_row)
        system_prompt = await self.build_system_prompt()
        await redis_cache.set_messages(
            self.redis, session_row.id, [{"role": "system", "content": system_prompt}]
        )
        return session_row

    async def list_sessions(self, user_id: uuid.UUID) -> list[Session]:
        return await session_repo.list_sessions_by_user(self.db, user_id)

    async def get_owned_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> Session:
        session_row = await session_repo.get_session_by_id(self.db, session_id)
        if session_row is None:
            raise SessionNotFound()
        if session_row.user_id != user_id:
            raise NotSessionOwner()
        return session_row

    async def add_turn(
        self, session_id: uuid.UUID, user_id: uuid.UUID, audio_bytes: bytes
    ) -> tuple[Turn, str, str | None, str, list[Correction]]:
        session_row = await self.get_owned_session(session_id, user_id)
        if session_row.status != "active":
            raise SessionClosed()

        stt_reply = await self.broker.call(STT_QUEUE, {}, audio=audio_bytes)
        transcript: str = stt_reply["text"]
        language: str | None = stt_reply.get("language")

        user_turn_id = uuid.uuid4()
        user_audio_path = audio_storage.save_audio(session_id, user_turn_id, audio_bytes)
        user_turn = await turn_repo.create_turn(
            self.db,
            Turn(
                id=user_turn_id,
                session_id=session_id,
                role="user",
                text=transcript,
                language=language,
                audio_path=user_audio_path,
            ),
        )

        # English only: a non-English turn skips the LLM and never touches the tutor's
        # rolling context; everything below (corrections, persistence, TTS) is shared.
        if is_english(language):
            messages = await redis_cache.get_messages(self.redis, session_id)
            if not messages:
                messages = [{"role": "system", "content": await self.build_system_prompt()}]
                for past in await turn_repo.list_turns_by_session(self.db, session_id):
                    messages.append({"role": past.role, "content": past.text})
            llm_reply = await self.broker.call(
                LLM_QUEUE,
                {
                    "system": messages[0]["content"],
                    "history": self.llm_history(messages),
                    "user": transcript,
                },
            )
            spoken_reply: str = llm_reply["spoken_reply"]
            raw_corrections = llm_reply.get("corrections", [])
            await redis_cache.set_messages(
                self.redis,
                session_id,
                messages
                + [
                    {"role": "user", "content": transcript},
                    {"role": "assistant", "content": spoken_reply},
                ],
            )
        else:
            spoken_reply = ENGLISH_ONLY_REPLY
            raw_corrections = []

        corrections = await correction_repo.create_corrections(
            self.db,
            [
                Correction(
                    turn_id=user_turn.id,
                    topic=item.get("topic", ""),
                    you_said=item["you_said"],
                    better=item["better"],
                    note=item["note"],
                )
                for item in raw_corrections
            ],
        )
        await MistakeService(self.db).log_mistakes(
            user_id, session_id, user_turn.id, raw_corrections
        )
        assistant_turn_id = uuid.uuid4()
        assistant_audio_path = str(audio_storage.audio_path(session_id, assistant_turn_id))
        assistant_turn = await turn_repo.create_turn(
            self.db,
            Turn(
                id=assistant_turn_id,
                session_id=session_id,
                role="assistant",
                text=spoken_reply,
                audio_path=assistant_audio_path,
            ),
        )
        try:
            tts_reply = await self.broker.call(
                TTS_QUEUE, {"text": spoken_reply}, timeout=8.0
            )
            audio_storage.save_audio(
                session_id, assistant_turn_id, tts_reply["audio"]
            )
        except Exception:
            logger.warning("TTS unavailable; assistant reply saved without audio")

        return assistant_turn, transcript, language, spoken_reply, corrections

    async def run_turn_stream(
        self, session_id: uuid.UUID, user_id: uuid.UUID, audio_bytes: bytes
    ) -> AsyncIterator[dict]:
        """Same pipeline as `add_turn`, but yields events for progressive WS delivery.

        Emits: `user_turn` (after STT) -> `assistant_turn` (after LLM, with corrections)
        -> `audio` (after TTS, best-effort). Persistence is identical to `add_turn`.
        """
        # 1) STT
        stt_reply = await self.broker.call(STT_QUEUE, {}, audio=audio_bytes)
        transcript: str = stt_reply["text"]
        language: str | None = stt_reply.get("language")

        # 2) persist user turn + audio
        user_turn_id = uuid.uuid4()
        user_audio_path = audio_storage.save_audio(session_id, user_turn_id, audio_bytes)
        user_turn = await turn_repo.create_turn(
            self.db,
            Turn(
                id=user_turn_id,
                session_id=session_id,
                role="user",
                text=transcript,
                language=language,
                audio_path=user_audio_path,
            ),
        )
        yield {
            "type": "user_turn",
            "id": str(user_turn_id),
            "text": transcript,
            "language": language,
            "audio_url": turn_audio_url(session_id, user_turn_id),
            "created_at": user_turn.created_at.isoformat(),
        }

        # 3) LLM: full context -> structured reply (rebuild from DB if Redis expired)
        messages = await redis_cache.get_messages(self.redis, session_id)
        if not messages:
            messages = [{"role": "system", "content": await self.build_system_prompt()}]
            for past in await turn_repo.list_turns_by_session(self.db, session_id):
                messages.append({"role": past.role, "content": past.text})
        llm_reply = await self.broker.call(
            LLM_QUEUE,
            {
                "system": messages[0]["content"],
                "history": self.llm_history(messages),
                "user": transcript,
            },
        )
        spoken_reply: str = llm_reply["spoken_reply"]
        raw_corrections = llm_reply.get("corrections", [])

        # 4) persist corrections + mistakes + assistant turn; refresh Redis context
        corrections = await correction_repo.create_corrections(
            self.db,
            [
                Correction(
                    turn_id=user_turn.id,
                    topic=item.get("topic", ""),
                    you_said=item["you_said"],
                    better=item["better"],
                    note=item["note"],
                )
                for item in raw_corrections
            ],
        )
        await MistakeService(self.db).log_mistakes(
            user_id, session_id, user_turn.id, raw_corrections
        )
        assistant_turn_id = uuid.uuid4()
        assistant_audio_path = str(audio_storage.audio_path(session_id, assistant_turn_id))
        assistant_turn = await turn_repo.create_turn(
            self.db,
            Turn(
                id=assistant_turn_id,
                session_id=session_id,
                role="assistant",
                text=spoken_reply,
                audio_path=assistant_audio_path,
            ),
        )
        await redis_cache.set_messages(
            self.redis,
            session_id,
            messages
            + [
                {"role": "user", "content": transcript},
                {"role": "assistant", "content": spoken_reply},
            ],
        )
        yield {
            "type": "assistant_turn",
            "id": str(assistant_turn_id),
            "text": spoken_reply,
            "corrections": [
                {
                    "id": str(c.id),
                    "topic": c.topic,
                    "you_said": c.you_said,
                    "better": c.better,
                    "note": c.note,
                }
                for c in corrections
            ],
            "created_at": assistant_turn.created_at.isoformat(),
        }

        # 5) TTS best-effort — voice the reply if a worker is up
        try:
            tts_reply = await self.broker.call(
                TTS_QUEUE, {"text": spoken_reply}, timeout=8.0
            )
            audio_storage.save_audio(
                session_id, assistant_turn_id, tts_reply["audio"]
            )
            yield {
                "type": "audio",
                "turn_id": str(assistant_turn_id),
                "audio_url": turn_audio_url(session_id, assistant_turn_id),
            }
        except Exception:
            logger.warning("TTS unavailable; assistant reply saved without audio")

    async def _synthesize(self, text: str) -> bytes | None:
        """Best-effort per-sentence TTS: raw WAV bytes, or None if a worker is unavailable."""
        try:
            reply = await self.broker.call(TTS_QUEUE, {"text": text}, timeout=8.0)
            return bytes(reply["audio"])
        except Exception:
            logger.warning("TTS unavailable for a sentence; skipping its audio")
            return None

    async def run_turn_realtime(
        self, session_id: uuid.UUID, user_id: uuid.UUID, audio_bytes: bytes
    ) -> AsyncIterator[dict]:
        """Realtime turn (E4): STT -> streamed reply voiced per sentence + a corrections pass.

        Emits: `user_turn` -> (`reply_delta` / `audio_chunk`)* -> `assistant_done`
        -> `corrections`. The spoken reply streams token-by-token and each finished
        sentence is voiced immediately, so the tutor starts speaking before the model has
        finished writing; grammar corrections are computed by a separate call in parallel.
        """
        # 1) STT
        stt_reply = await self.broker.call(STT_QUEUE, {}, audio=audio_bytes)
        transcript: str = stt_reply["text"].strip()
        language: str | None = stt_reply.get("language")

        # A silence (or an echo of the tutor's own voice) can endpoint into an empty
        # transcript — skip it so we never send an empty user turn to the LLM.
        if not transcript:
            logger.info("Empty transcript; skipping realtime turn")
            return

        # 2) persist the user turn + audio
        user_turn_id = uuid.uuid4()
        user_audio_path = audio_storage.save_audio(session_id, user_turn_id, audio_bytes)
        user_turn = await turn_repo.create_turn(
            self.db,
            Turn(
                id=user_turn_id,
                session_id=session_id,
                role="user",
                text=transcript,
                language=language,
                audio_path=user_audio_path,
            ),
        )
        yield {
            "type": "user_turn",
            "id": str(user_turn_id),
            "text": transcript,
            "language": language,
            "audio_url": turn_audio_url(session_id, user_turn_id),
            "created_at": user_turn.created_at.isoformat(),
        }

        # 3) voice() is shared; only how we produce the reply differs by language.
        audio_chunks: list[bytes] = []

        async def voice(sentence: str) -> AsyncIterator[dict]:
            wav = await self._synthesize(sentence)
            if wav is not None:
                audio_chunks.append(wav)
                yield {
                    "type": "audio_chunk",
                    "text": sentence,
                    "audio_b64": base64.b64encode(wav).decode(),
                }

        if is_english(language):
            # rebuild the conversation history (Redis hot context, or from the DB)
            messages = await redis_cache.get_messages(self.redis, session_id)
            if not messages:
                messages = [{"role": "system", "content": await self.build_system_prompt()}]
                for past in await turn_repo.list_turns_by_session(self.db, session_id):
                    messages.append({"role": past.role, "content": past.text})
            # TEMPORARY: the experiment picks the window and the caching flag.
            # Restore `history = self.llm_history(messages)` when it is over.
            # Flip USE_POLICY_SET_2 to run the token-budget set instead of the turn set.
            if USE_POLICY_SET_2:
                history, use_cache, mode = reply_policy_2(messages), True, "stream_reply_2"
            else:
                history, use_cache = reply_policy(messages)
                mode = "stream_reply"

            # corrections run in parallel (network only — no DB touch off the main coroutine).
            # No history: the pass grades the learner's latest message on its own, so the
            # conversation adds input tokens and latency without changing the verdict.
            # Only `stream` keeps the history it needs to hold a conversation.
            corrections_task: asyncio.Task[dict] | None = asyncio.create_task(
                self.broker.call(
                    LLM_QUEUE,
                    {
                        "mode": "corrections",
                        "system": await self.build_corrections_prompt(),
                        "history": [],
                        "user": transcript,
                    },
                )
            )

            # stream the spoken reply; voice each finished sentence as it completes
            aggregator = SentenceAggregator()
            reply_parts: list[str] = []
            async for chunk in self.broker.call_stream(
                LLM_QUEUE,
                {
                    "mode": mode,  # TEMPORARY: experiment picks the handler
                    "system": REALTIME_REPLY_PROMPT,
                    "history": history,
                    "user": transcript,
                    "cache": use_cache,  # TEMPORARY: experiment flag
                    "policy": REPLY_POLICY_2 if USE_POLICY_SET_2 else REPLY_POLICY,
                },
            ):
                delta = chunk.get("delta", "")
                if not delta:
                    continue
                reply_parts.append(delta)
                yield {"type": "reply_delta", "text": delta}
                for sentence in aggregator.feed(delta):
                    async for event in voice(sentence):
                        yield event
            tail = aggregator.flush()
            if tail:
                async for event in voice(tail):
                    yield event
            spoken_reply = "".join(reply_parts).strip()

            # only a real (English) turn updates the tutor's rolling context
            await redis_cache.set_messages(
                self.redis,
                session_id,
                messages
                + [
                    {"role": "user", "content": transcript},
                    {"role": "assistant", "content": spoken_reply},
                ],
            )
        else:
            # English only: skip the LLM entirely and voice one canned line.
            corrections_task = None
            spoken_reply = ENGLISH_ONLY_REPLY
            async for event in voice(spoken_reply):
                yield event

        # persist the assistant turn + concatenated audio
        assistant_turn_id = uuid.uuid4()
        assistant_audio_path: str | None = None
        if audio_chunks:
            assistant_audio_path = audio_storage.save_audio(
                session_id, assistant_turn_id, concat_wavs(audio_chunks)
            )
        assistant_turn = await turn_repo.create_turn(
            self.db,
            Turn(
                id=assistant_turn_id,
                session_id=session_id,
                role="assistant",
                text=spoken_reply,
                audio_path=assistant_audio_path,
            ),
        )
        yield {
            "type": "assistant_done",
            "id": str(assistant_turn_id),
            "text": spoken_reply,
            "audio_url": (
                turn_audio_url(session_id, assistant_turn_id)
                if assistant_audio_path
                else None
            ),
            "created_at": assistant_turn.created_at.isoformat(),
        }

        # 7) corrections: persist + emit once the parallel pass returns (none for a
        # non-English turn, which never ran the LLM)
        raw_corrections = (
            (await corrections_task).get("corrections", [])
            if corrections_task is not None
            else []
        )
        corrections = await correction_repo.create_corrections(
            self.db,
            [
                Correction(
                    turn_id=user_turn.id,
                    topic=item.get("topic", ""),
                    you_said=item["you_said"],
                    better=item["better"],
                    note=item["note"],
                )
                for item in raw_corrections
            ],
        )
        await MistakeService(self.db).log_mistakes(
            user_id, session_id, user_turn.id, raw_corrections
        )
        yield {
            "type": "corrections",
            "turn_id": str(user_turn_id),
            "corrections": [
                {
                    "id": str(c.id),
                    "topic": c.topic,
                    "you_said": c.you_said,
                    "better": c.better,
                    "note": c.note,
                }
                for c in corrections
            ],
        }

    async def close_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> Session:
        session_row = await self.get_owned_session(session_id, user_id)
        session_row.status = "closed"
        session_row.closed_at = datetime.now(timezone.utc)
        session_row = await session_repo.update_session(self.db, session_row)
        await redis_cache.clear_messages(self.redis, session_id)
        return session_row
