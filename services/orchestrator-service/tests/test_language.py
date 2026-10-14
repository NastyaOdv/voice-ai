"""Language gating for the pipeline: only English turns reach the LLM."""
from app.services.session_service import is_english


def test_english_codes_pass():
    assert is_english("en")
    assert is_english("en-US")  # region suffix still counts as English
    assert is_english("EN")  # case-insensitive


def test_unknown_language_passes():
    # A failed/absent STT detection must not block a genuine English turn.
    assert is_english(None)


def test_non_english_is_blocked():
    assert not is_english("ru")
    assert not is_english("es")
    assert not is_english("uk")
