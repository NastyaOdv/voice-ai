"""Stepped history window: how much of the session reaches the LLM each turn.

The window is cut in steps rather than slid one pair at a time, because prompt caching
matches on an exact prefix: a window that drops its oldest pair every turn moves the
start of the conversation every turn and invalidates the cache on every call.
"""
from app.utils.history import trim_history

MAX_PAIRS = 30   # cut once the history grows past this
KEEP_PAIRS = 15  # ...back to this


def make_history(pairs: int) -> list[dict[str, str]]:
    """`pairs` alternating user/assistant messages, numbered so order is checkable."""
    history: list[dict[str, str]] = []
    for i in range(pairs):
        history.append({"role": "user", "content": f"u{i}"})
        history.append({"role": "assistant", "content": f"a{i}"})
    return history


def trim(pairs: int) -> list[dict[str, str]]:
    return trim_history(make_history(pairs), max_pairs=MAX_PAIRS, keep_pairs=KEEP_PAIRS)


def test_history_below_the_high_water_mark_is_unchanged():
    history = make_history(29)
    assert trim_history(history, max_pairs=MAX_PAIRS, keep_pairs=KEEP_PAIRS) == history


def test_history_past_the_mark_is_cut_back_to_keep_pairs():
    trimmed = trim(30)
    assert len(trimmed) == KEEP_PAIRS * 2
    assert trimmed[0] == {"role": "user", "content": "u15"}
    assert trimmed[-1] == {"role": "assistant", "content": "a29"}


def test_window_start_is_stable_between_steps():
    # The whole point of stepping. Across one step's worth of turns the first message
    # must not move, or the cached prefix is thrown away on every call.
    starts = {trim(p)[0]["content"] for p in range(30, 45)}
    assert starts == {"u15"}, starts


def test_window_start_moves_once_per_step():
    # ...but it must eventually move, or the history grows without bound.
    starts = [trim(p)[0]["content"] for p in range(30, 60)]
    assert starts[0] == "u15"
    assert starts[-1] == "u30"
    assert len(set(starts)) == 2


def test_history_never_exceeds_the_mark_by_more_than_a_step():
    for pairs in range(1, 120):
        assert len(trim(pairs)) <= MAX_PAIRS * 2


def test_trimmed_history_starts_with_a_user_message():
    # A user turn is persisted before the LLM is called, so a failed call leaves an
    # unpaired tail and the window can land mid-pair. The Anthropic API rejects a
    # conversation whose first message is not `user`.
    for pairs in range(30, 60):
        history = [*make_history(pairs), {"role": "user", "content": "tail"}]
        trimmed = trim_history(history, max_pairs=MAX_PAIRS, keep_pairs=KEEP_PAIRS)
        assert trimmed[0]["role"] == "user", pairs


def test_zero_max_pairs_disables_trimming():
    history = make_history(50)
    assert trim_history(history, max_pairs=0, keep_pairs=KEEP_PAIRS) == history


def test_empty_history_stays_empty():
    assert trim_history([], max_pairs=MAX_PAIRS, keep_pairs=KEEP_PAIRS) == []


def test_keep_pairs_at_least_the_mark_degrades_to_no_trimming():
    # Misconfiguration guard: keeping as much as the mark can never cut anything, so
    # treat it as disabled instead of looping or emptying the history.
    history = make_history(50)
    assert trim_history(history, max_pairs=20, keep_pairs=20) == history


def test_trimming_does_not_mutate_the_input():
    history = make_history(50)
    trim_history(history, max_pairs=MAX_PAIRS, keep_pairs=KEEP_PAIRS)
    assert len(history) == 100
