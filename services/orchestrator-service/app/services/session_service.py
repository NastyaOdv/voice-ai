import asyncio
import base64
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.logger.logger_config import logger
from app.models import Correction, Session, Turn
from app.repositories import correction_repo, session_repo, turn_repo
from app.services.mistake_service import MistakeService
from app.utils import audio_storage, redis_cache
from app.utils.audio import concat_wavs
from app.utils.exceptions import NotSessionOwner, SessionClosed, SessionNotFound
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
    "You are a friendly spoken-English tutor on a live voice call. Reply with a single "
    "natural spoken line that continues the conversation. Do NOT mention grammar "
    "mistakes or corrections. Do not include internal or system XML tags in your reply."
)
CORRECTIONS_PROMPT = (
    "You review the learner's latest message and list only their GRAMMAR mistakes, each "
    "an object with 'topic', 'you_said', 'better' and 'note'. Return an empty list if "
    "there are none."
)


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

        # 1) STT: audio -> verbatim text (+ detected language)
        stt_reply = await self.broker.call(
            STT_QUEUE, {"audio_b64": base64.b64encode(audio_bytes).decode()}
        )
        transcript: str = stt_reply["text"]
        language: str | None = stt_reply.get("language")

        # 2) persist the user turn and its audio
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

        # 3) LLM: full context -> structured reply. Rebuild context from the DB if the
        #    Redis cache has expired mid-session. We own the domain content and state
        #    (system[0] + history); the LLM service assembles the vendor request.
        messages = await redis_cache.get_messages(self.redis, session_id)
        if not messages:
            messages = [{"role": "system", "content": await self.build_system_prompt()}]
            for past in await turn_repo.list_turns_by_session(self.db, session_id):
                messages.append({"role": past.role, "content": past.text})
        llm_reply = await self.broker.call(
            LLM_QUEUE,
            {
                "system": messages[0]["content"],
                "history": messages[1:],
                "user": transcript,
            },
        )
        spoken_reply: str = llm_reply["spoken_reply"]

        # 4) persist the LLM's work FIRST — grammar corrections + the assistant reply
        #    text — so it is never lost if TTS is slow or unavailable.
        raw_corrections = llm_reply.get("corrections", [])
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
        # Also log each mistake against the user (per-user error profile across sessions).
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

        # 5) refresh the hot context in Redis (system[0] + full turn history)
        await redis_cache.set_messages(
            self.redis,
            session_id,
            messages
            + [
                {"role": "user", "content": transcript},
                {"role": "assistant", "content": spoken_reply},
            ],
        )

        # 6) TTS is best-effort: voice the spoken_reply if a worker is available, but
        #    never block the reply on it (short timeout so a missing worker fails fast).
        try:
            tts_reply = await self.broker.call(
                TTS_QUEUE, {"text": spoken_reply}, timeout=8.0
            )
            audio_storage.save_audio(
                session_id, assistant_turn_id, base64.b64decode(tts_reply["audio_b64"])
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
        stt_reply = await self.broker.call(
            STT_QUEUE, {"audio_b64": base64.b64encode(audio_bytes).decode()}
        )
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
                "history": messages[1:],
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
                session_id, assistant_turn_id, base64.b64decode(tts_reply["audio_b64"])
            )
            yield {
                "type": "audio",
                "turn_id": str(assistant_turn_id),
                "audio_url": turn_audio_url(session_id, assistant_turn_id),
            }
        except Exception:
            logger.warning("TTS unavailable; assistant reply saved without audio")

    async def _synthesize(self, text: str) -> str | None:
        """Best-effort per-sentence TTS: base64 WAV, or None if a worker is unavailable."""
        try:
            reply = await self.broker.call(TTS_QUEUE, {"text": text}, timeout=8.0)
            return str(reply["audio_b64"])
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
        stt_reply = await self.broker.call(
            STT_QUEUE, {"audio_b64": base64.b64encode(audio_bytes).decode()}
        )
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

        # 3) rebuild the conversation history (Redis hot context, or from the DB)
        messages = await redis_cache.get_messages(self.redis, session_id)
        if not messages:
            messages = [{"role": "system", "content": await self.build_system_prompt()}]
            for past in await turn_repo.list_turns_by_session(self.db, session_id):
                messages.append({"role": past.role, "content": past.text})
        history = messages[1:]

        # 4) corrections run in parallel (network only — no DB touch off the main coroutine)
        corrections_task = asyncio.create_task(
            self.broker.call(
                LLM_QUEUE,
                {
                    "mode": "corrections",
                    "system": await self.build_corrections_prompt(),
                    "history": history,
                    "user": transcript,
                },
            )
        )

        # 5) stream the spoken reply; voice each finished sentence as it completes
        aggregator = SentenceAggregator()
        audio_chunks: list[bytes] = []
        reply_parts: list[str] = []
        reply_system = REALTIME_REPLY_PROMPT

        async def voice(sentence: str) -> AsyncIterator[dict]:
            audio_b64 = await self._synthesize(sentence)
            if audio_b64 is not None:
                audio_chunks.append(base64.b64decode(audio_b64))
                yield {"type": "audio_chunk", "text": sentence, "audio_b64": audio_b64}

        async for chunk in self.broker.call_stream(
            LLM_QUEUE,
            {"mode": "stream_reply", "system": reply_system, "history": history, "user": transcript},
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

        # 6) persist the assistant turn + concatenated audio; refresh Redis context
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

        # 7) corrections: persist + emit once the parallel pass returns
        corr_reply = await corrections_task
        raw_corrections = corr_reply.get("corrections", [])
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
