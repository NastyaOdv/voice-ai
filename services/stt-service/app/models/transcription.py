from typing import TypedDict


class Transcription(TypedDict):
    text: str
    language: str
    language_probability: float
