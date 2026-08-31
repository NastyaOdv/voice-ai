import io
import wave

DEFAULT_SAMPLE_RATE = 16000


def pcm16_to_wav(pcm: bytes, sample_rate: int, channels: int = 1) -> bytes:
    """Wrap raw 16-bit little-endian PCM in a WAV container.

    The realtime WS receives headerless PCM frames; STT (faster-whisper) needs a real
    container, so we wrap each detected utterance before sending it to the worker.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


def concat_wavs(chunks: list[bytes]) -> bytes:
    """Concatenate several PCM16 WAVs (one per sentence) into a single WAV.

    Used to persist the streamed per-sentence TTS as one replayable clip on the
    assistant turn. Chunks are assumed mono/16-bit at the same rate; the output adopts
    the first chunk's rate (default 16 kHz when the list is empty).
    """
    pcm = bytearray()
    sample_rate = DEFAULT_SAMPLE_RATE
    channels = 1
    for i, chunk in enumerate(chunks):
        with wave.open(io.BytesIO(chunk), "rb") as wav_file:
            if i == 0:
                sample_rate = wav_file.getframerate()
                channels = wav_file.getnchannels()
            pcm.extend(wav_file.readframes(wav_file.getnframes()))
    return pcm16_to_wav(bytes(pcm), sample_rate, channels)
