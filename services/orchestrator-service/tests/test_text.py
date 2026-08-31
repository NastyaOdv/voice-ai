"""Tests for streaming sentence segmentation (T4.1)."""
from app.utils.text import SentenceAggregator


def test_emits_a_sentence_once_terminal_punctuation_is_confirmed():
    agg = SentenceAggregator()
    assert agg.feed("Hello there") == []  # no terminator yet
    assert agg.feed(". ") == ["Hello there."]  # '.' + space confirms the boundary


def test_reassembles_a_sentence_split_across_deltas():
    agg = SentenceAggregator()
    assert agg.feed("Hel") == []
    assert agg.feed("lo. Wor") == ["Hello."]
    assert agg.feed("ld!") == []  # '!' at the very end is not confirmed yet
    assert agg.flush() == "World!"


def test_multiple_sentences_in_one_delta():
    agg = SentenceAggregator()
    assert agg.feed("Nice. Good job! Right? ") == ["Nice.", "Good job!", "Right?"]
    assert agg.flush() is None


def test_does_not_split_on_a_decimal_point():
    agg = SentenceAggregator()
    # No space after the dot, so "3.14" is not a boundary; the sentence completes later.
    assert agg.feed("Pi is 3.14 exactly. ") == ["Pi is 3.14 exactly."]


def test_newline_after_punctuation_is_a_boundary():
    agg = SentenceAggregator()
    assert agg.feed("Line one.\nLine two") == ["Line one."]
    assert agg.flush() == "Line two"


def test_flush_returns_none_when_empty():
    agg = SentenceAggregator()
    assert agg.flush() is None
    agg.feed("Done. ")
    assert agg.flush() is None


def test_keeps_a_trailing_closing_quote_with_the_sentence():
    agg = SentenceAggregator()
    assert agg.feed('He said "go home." Now') == ['He said "go home."']
