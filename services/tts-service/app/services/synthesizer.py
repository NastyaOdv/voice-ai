"""Piper text-to-speech. The voice model is loaded once and reused.

Piper is a fast, CPU-friendly neural TTS. We stream raw 16-bit PCM out of the voice
and wrap it in a WAV container ourselves, so the orchestrator gets ready-to-serve
`audio/wav` bytes (the same media type the assistant-audio endpoint returns).
"""
import io
import wave
from functools import lru_cache

from piper import PiperVoice

from app.conf.config import get_settings
from app.logger.logger_config import logger


@lru_cache
def get_voice() -> PiperVoice:
    settings = get_settings()
    logger.info(f"Loading Piper voice '{settings.model_path}'")
    return PiperVoice.load(settings.model_path)


def synthesize(text: str) -> bytes:
    """Synthesize `text` into WAV bytes (mono, 16-bit PCM at the voice's sample rate)."""
    voice = get_voice()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(voice.config.sample_rate)
        for chunk in voice.synthesize_stream_raw(text):
            wav_file.writeframes(chunk)
    return buffer.getvalue()
