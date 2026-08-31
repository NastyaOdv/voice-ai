"""Streaming sentence segmentation for the realtime call (E4).

The LLM reply arrives as a token stream; we buffer it and emit whole sentences as soon
as a terminal punctuation is *confirmed* by a following whitespace (or newline). Waiting
for that following character both avoids splitting decimals like "3.14" and defers the
final sentence until it is really complete — the leftover is returned by `flush()`.
"""

TERMINALS = ".!?…"
# Closing marks that belong to the sentence they trail (kept before the boundary).
CLOSERS = "\"')]}”’»"


class SentenceAggregator:
    def __init__(self) -> None:
        self._buf = ""

    def feed(self, delta: str) -> list[str]:
        """Append `delta`; return any sentences whose boundary is now confirmed."""
        self._buf += delta
        sentences: list[str] = []
        while (boundary := self._find_boundary()) is not None:
            sentence = self._buf[:boundary].strip()
            if sentence:
                sentences.append(sentence)
            self._buf = self._buf[boundary:].lstrip()
        return sentences

    def flush(self) -> str | None:
        """Return the buffered remainder (if any) and clear the buffer."""
        remainder = self._buf.strip()
        self._buf = ""
        return remainder or None

    def _find_boundary(self) -> int | None:
        """Index at which to cut, or None if no confirmed boundary yet.

        A boundary is a run of terminal punctuation (plus trailing closers) followed by
        whitespace. The returned index points at that whitespace, so it stays out of the
        emitted sentence and is stripped from the remaining buffer.
        """
        for i, ch in enumerate(self._buf):
            if ch not in TERMINALS:
                continue
            j = i + 1
            while j < len(self._buf) and self._buf[j] in TERMINALS + CLOSERS:
                j += 1
            if j >= len(self._buf):
                return None  # nothing after the punctuation yet — wait for more input
            if self._buf[j].isspace():
                return j
            # e.g. the '.' in "3.14": not a boundary, keep scanning.
        return None
