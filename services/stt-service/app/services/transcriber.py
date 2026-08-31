"""faster-whisper transcription. The model is loaded once and reused.

Verbatim on purpose: we transcribe exactly what the learner said so grammar mistakes
survive into the text (no cleanup / normalization). We also return the detected
language so the orchestrator can store it (useful to spot a learner slipping into
their native tongue).
"""
import io
from functools import lru_cache

from faster_whisper import WhisperModel

from app.conf.config import get_settings
from app.logger.logger_config import logger
from app.models import Transcription


@lru_cache
def get_model() -> WhisperModel:
    settings = get_settings()
    logger.info(
        f"Loading faster-whisper '{settings.model_size}' "
        f"on {settings.device} ({settings.compute_type})"
    )
    return WhisperModel(
        settings.model_size, device=settings.device, compute_type=settings.compute_type
    )


def transcribe(audio_bytes: bytes) -> Transcription:
    settings = get_settings()
    model = get_model()
    segments, info = model.transcribe(io.BytesIO(audio_bytes), beam_size=settings.beam_size)
    text = " ".join(segment.text.strip() for segment in segments).strip()
    return {
        "text": text,
        "language": info.language,
        "language_probability": float(info.language_probability),
    }
