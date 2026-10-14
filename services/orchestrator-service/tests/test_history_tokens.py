"""Token-budget history window: the unit that actually drives cost and caching.

A window measured in turns is not the same window twice — one exchange has measured
anywhere from 100 to 222 tokens depending on how talkative the learner is, so a fixed
pair count lands above the cache minimum in one conversation and below it in another.
This window is measured in tokens and cut in steps, with a floor in pairs so a verbose
learner cannot squeeze the conversation down to nothing.
"""
from app.utils.history import estimate_tokens, trim_history_tokens

KEEP = 400
MAX = 1000        # шаг = 600 токенов = 6 пар по 100


def pair(i: int, size: int = 100) -> list[dict[str, str]]:
    """One user/assistant pair of roughly `size` tokens total (4 chars per token)."""
    body = "x" * (size * 4 // 2)
    return [
        {"role": "user", "content": f"u{i}{body}"},
        {"role": "assistant", "content": f"a{i}{body}"},
    ]


def history(pairs: int, size: int = 100) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for i in range(pairs):
        out += pair(i, size)
    return out


def trim(pairs: int, size: int = 100, **kw) -> list[dict[str, str]]:
    return trim_history_tokens(
        history(pairs, size), keep_tokens=KEEP, max_tokens=MAX, **kw
    )


def test_history_under_the_budget_is_unchanged():
    h = history(4)                      # ~400 tokens, below MAX
    assert trim_history_tokens(h, keep_tokens=KEEP, max_tokens=MAX) == h


def test_history_over_the_budget_is_cut_back_to_keep_tokens():
    # The cut drops whole steps, so the window oscillates between KEEP and MAX rather
    # than snapping to KEEP exactly — the same shape the pair-based window has.
    trimmed = trim(12)                  # ~1200 tokens, over MAX
    assert KEEP <= estimate_tokens(trimmed) <= MAX
    assert trimmed[-1]["content"].startswith("a11")  # newest pair survives


def test_window_start_is_stable_between_cuts():
    # The point of stepping: while the history sits between KEEP and MAX nothing is
    # dropped, so the cached prefix stays put.
    starts = {trim(p)[0]["content"][:3] for p in range(10, 16)}
    assert len(starts) == 1, starts


def test_window_start_moves_when_the_budget_is_exceeded_again():
    assert trim(10)[0]["content"][:3] != trim(20)[0]["content"][:3]


def test_min_pairs_floor_beats_the_budget():
    # A verbose learner: each pair alone eats the whole budget. Without a floor the
    # window would collapse to one exchange and the tutor would lose the thread.
    trimmed = trim(20, size=500, min_pairs=8)
    assert len(trimmed) == 8 * 2
    assert estimate_tokens(trimmed) > KEEP      # floor deliberately overruns the budget


def test_pinned_opening_pairs_are_always_kept():
    trimmed = trim(20, pin_pairs=2)
    assert trimmed[0]["content"].startswith("u0")
    assert trimmed[2]["content"].startswith("u1")
    assert trimmed[-1]["content"].startswith("a19")


def test_pinned_prefix_never_moves():
    # Pinned pairs are a permanently stable prefix, so they stay cacheable across cuts.
    starts = {tuple(m["content"][:3] for m in trim(p, pin_pairs=2)[:4]) for p in (12, 20, 30)}
    assert len(starts) == 1, starts


def test_result_starts_with_a_user_message():
    for pairs in range(1, 30):
        for kw in ({}, {"pin_pairs": 2}, {"min_pairs": 8}):
            trimmed = trim(pairs, **kw)
            assert not trimmed or trimmed[0]["role"] == "user", (pairs, kw)


def test_zero_max_tokens_disables_trimming():
    h = history(50)
    assert trim_history_tokens(h, keep_tokens=KEEP, max_tokens=0) == h


def test_empty_history_stays_empty():
    assert trim_history_tokens([], keep_tokens=KEEP, max_tokens=MAX) == []


def test_trimming_does_not_mutate_the_input():
    h = history(30)
    trim_history_tokens(h, keep_tokens=KEEP, max_tokens=MAX)
    assert len(h) == 60
