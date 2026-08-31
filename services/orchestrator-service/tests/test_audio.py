"""Tests for audio helpers (T4.2: concatenating per-sentence TTS WAVs)."""
import wave
from io import BytesIO

from app.utils.audio import concat_wavs, pcm16_to_wav

RATE = 16000


def _read(wav: bytes) -> tuple[int, int, bytes]:
    with wave.open(BytesIO(wav), "rb") as w:
        return w.getframerate(), w.getnframes(), w.readframes(w.getnframes())


def test_concat_wavs_sums_frames_and_preserves_pcm_order():
    a = pcm16_to_wav(b"\x01\x00" * 100, RATE)  # 100 frames
    b = pcm16_to_wav(b"\x02\x00" * 150, RATE)  # 150 frames

    combined = concat_wavs([a, b])

    rate, nframes, pcm = _read(combined)
    assert rate == RATE
    assert nframes == 250
    assert pcm == b"\x01\x00" * 100 + b"\x02\x00" * 150


def test_concat_wavs_single_chunk_roundtrips():
    a = pcm16_to_wav(b"\x07\x00" * 32, RATE)
    rate, nframes, pcm = _read(concat_wavs([a]))
    assert (rate, nframes) == (RATE, 32)
    assert pcm == b"\x07\x00" * 32


def test_concat_wavs_empty_list_returns_valid_silent_wav():
    rate, nframes, pcm = _read(concat_wavs([]))
    assert nframes == 0
    assert pcm == b""
