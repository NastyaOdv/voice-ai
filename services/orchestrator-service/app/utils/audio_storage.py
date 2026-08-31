"""Local audio storage. Files live under STORAGE_DIR/<session_id>/<turn_id>.wav.

Level 1 keeps audio on the local disk (a mounted volume). Swapping this for MinIO/S3
later only touches this module.
"""
import uuid
from collections.abc import Iterator
from pathlib import Path

from app.conf.config import get_settings

CHUNK_SIZE = 64 * 1024


def audio_path(session_id: uuid.UUID, turn_id: uuid.UUID) -> Path:
    return Path(get_settings().storage_dir) / str(session_id) / f"{turn_id}.wav"


def save_audio(session_id: uuid.UUID, turn_id: uuid.UUID, data: bytes) -> str:
    path = audio_path(session_id, turn_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return str(path)


def read_audio(path: str) -> bytes:
    return Path(path).read_bytes()


def iter_audio(path: Path, start: int, end: int) -> Iterator[bytes]:
    """Yield bytes[start..end] of the file in chunks, without loading it all in memory."""
    with path.open("rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = f.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
