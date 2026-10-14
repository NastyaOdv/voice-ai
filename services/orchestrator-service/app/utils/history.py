

def trim_history(
    history: list[dict[str, str]], max_pairs: int, keep_pairs: int
) -> list[dict[str, str]]:
    step = max_pairs - keep_pairs
    if max_pairs <= 0 or step <= 0:
        return list(history)

    excess = len(history) // 2 - keep_pairs
    if excess < step:
        return list(history)

    return history[(excess // step) * step * 2 :]


def estimate_tokens(messages: list[dict[str, str]]) -> int:
    """Rough token count of a message list: ~4 characters per token.

    The same estimate the llm-service context log uses; checked against real usage
    figures it lands within a few percent, which is enough to steer a budget.
    """
    return sum(len(m.get("content", "")) for m in messages) // 4


def trim_history_tokens(
    history: list[dict[str, str]],
    keep_tokens: int,
    max_tokens: int,
    min_pairs: int = 0,
    pin_pairs: int = 0,
) -> list[dict[str, str]]:
    """Cut `history` back once it grows past `max_tokens`, in steps, measured in tokens.

    Tokens rather than turns because tokens are what the cache minimum and the price are
    denominated in: one exchange has measured between 100 and 222 tokens, so a fixed pair
    count gives no control over either — the same setting lands above the 4096 minimum in
    one conversation and below it in another.

    Between cuts nothing is dropped, so the prefix and the cache built on it stay put.
    `min_pairs` keeps the conversation usable when a verbose learner would otherwise be
    left with one exchange; `pin_pairs` holds the opening of the session (where learners
    introduce themselves) permanently, which also gives the request a prefix that never
    moves at all.

    `max_tokens <= 0` disables trimming. Pairs are dropped whole, so the result still
    starts on a `user` message.
    """
    step = max_tokens - keep_tokens
    total = estimate_tokens(history)
    if max_tokens <= 0 or step <= 0 or total <= max_tokens:
        return list(history)

    head = history[: pin_pairs * 2]
    tail = history[pin_pairs * 2 :]

    # Drop a whole number of steps' worth of tokens, not "everything above keep_tokens".
    # Quantising the cut is what makes this a step: the same amount is dropped for every
    # history between two step boundaries, so the window's first message stays put until
    # the next boundary is crossed. Cutting to exactly keep_tokens would move it on every
    # turn and invalidate the cache each time, which is the failure this design avoids.
    target = ((total - keep_tokens) // step) * step
    floor = max(len(tail) - min_pairs * 2, 0)

    dropped = 0
    start = 0
    while start < floor and dropped < target:
        dropped += estimate_tokens(tail[start : start + 2])
        start += 2
    return head + tail[start:]
