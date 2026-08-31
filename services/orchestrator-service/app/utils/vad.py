"""Voice-activity endpointing for the realtime WS.

Feeds a continuous PCM stream through WebRTC VAD frame by frame and emits utterance
boundaries: a `start` when speech begins, an `end` (with the buffered audio) once the
user has been silent long enough. This is what replaces the manual "Stop" button —
the server decides when the learner has finished speaking.
"""
from collections.abc import Iterator

import webrtcvad


class VadEndpointer:
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = 20,
        aggressiveness: int = 2,
        start_frames: int = 3,
        end_silence_ms: int = 700,
    ) -> None:
        self._vad = webrtcvad.Vad(aggressiveness)  # 0=lenient .. 3=aggressive
        self._sample_rate = sample_rate
        self._frame_bytes = int(sample_rate * frame_ms / 1000) * 2  # 16-bit mono
        self._start_frames = start_frames
        self._end_silence_frames = max(1, end_silence_ms // frame_ms)

        self._pending = bytearray()   # leftover bytes not yet a full frame
        self._utterance = bytearray()  # audio accumulated for the current utterance
        self._in_speech = False
        self._speech_run = 0
        self._silence_run = 0

    def feed(self, data: bytes) -> Iterator[tuple[str, bytes | None]]:
        """Feed raw PCM; yield ('start', None) / ('end', utterance_bytes) events."""
        self._pending.extend(data)
        while len(self._pending) >= self._frame_bytes:
            frame = bytes(self._pending[: self._frame_bytes])
            del self._pending[: self._frame_bytes]
            is_speech = self._vad.is_speech(frame, self._sample_rate)

            if not self._in_speech:
                if is_speech:
                    self._speech_run += 1
                    self._utterance.extend(frame)
                    if self._speech_run >= self._start_frames:
                        self._in_speech = True
                        self._silence_run = 0
                        yield ("start", None)
                else:
                    # keep a little leading audio so the first word is not clipped
                    self._speech_run = 0
                    self._utterance.clear()
            else:
                self._utterance.extend(frame)
                if is_speech:
                    self._silence_run = 0
                else:
                    self._silence_run += 1
                    if self._silence_run >= self._end_silence_frames:
                        utterance = bytes(self._utterance)
                        self._reset_utterance()
                        yield ("end", utterance)

    def _reset_utterance(self) -> None:
        self._utterance.clear()
        self._in_speech = False
        self._speech_run = 0
        self._silence_run = 0
