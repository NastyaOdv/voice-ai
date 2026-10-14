"""Reference depth: how far back a tutor reply actually has to look.

Step 0 of the history-window study. Before picking a window size we need to know
whether real conversations reference old turns at all. For every learner turn this
script asks a judge model the single question that matters: what is the oldest
earlier exchange the tutor must still have in order to answer this turn correctly?

The answer is expressed in PAIRS BACK, the same unit the window is configured in,
so the result maps straight onto a window size: a window of N pairs is safe for
every turn whose depth is <= N. The coverage table at the end reads directly as
"a window of N pairs would have been enough for X% of real turns".

Reads `or_turns` from Postgres and calls the judge through the LiteLLM proxy.
Read-only: nothing is written to the database.

TEMPORARY: analysis tool for the history-window experiment, delete when it concludes.

Usage:
    python scripts/reference_depth.py --limit 40                 # smoke run
    python scripts/reference_depth.py --out depth.csv            # full run
    python scripts/reference_depth.py --model claude-sonnet-4-5  # stronger judge
"""
import argparse
import asyncio
import csv
import os
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from dataclasses import dataclass

import httpx
import psycopg

JUDGE_SYSTEM = """You analyse a spoken-English tutoring conversation to measure how much \
history a reply needs.

You are shown earlier exchanges, each labelled with how many exchanges back it is
([-1] is the most recent one before the latest message), followed by the latest
learner message. Report the LARGEST label whose content the tutor still needs in
order to reply to that latest message correctly.

Be strict. An exchange counts as needed ONLY if, without it, the tutor would:
  - fail to resolve a reference in the latest message (a pronoun, a name, "that", \
"the one I mentioned"), or
  - repeat a question the learner has already answered, or
  - contradict or forget a fact the learner stated, or
  - answer a question that only makes sense against that earlier exchange.

Being merely topical, polite or nice to know does NOT count. General conversational
continuity does NOT count. If the latest message stands on its own, the depth is 0."""

# The schema is enforced by the API, not requested in the prompt: `tool_choice` forces
# this tool, so the model cannot answer with prose and the fields cannot come back
# missing or mistyped. Same mechanism the SDK's `messages.parse` is built on, without
# pulling the anthropic package into this venv just for one script.
DEPTH_TOOL = {
    "name": "report_reference_depth",
    "description": (
        "Report how far back the tutor must still look in order to answer the latest "
        "learner message correctly."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "depth": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "The largest [-N] label whose content is still needed. "
                    "0 when the latest message stands on its own."
                ),
            },
            "reason": {
                "type": "string",
                "description": "Why that exchange is needed, at most 12 words.",
            },
        },
        "required": ["depth", "reason"],
    },
}


@dataclass
class Probe:
    """One learner turn to be judged, with the history that precedes it."""

    session_id: str
    pair_index: int
    latest: str
    context_pairs: list[tuple[str, str]]


@dataclass
class Verdict:
    """The judge's answer for one probe."""

    session_id: str
    pair_index: int
    depth: int
    clamped: bool
    reason: str
    latest: str


def load_sessions(dsn: str, min_turns: int) -> dict[str, list[tuple[str, str]]]:
    """Read every session's turns from Postgres, longest sessions kept only."""
    query = (
        "SELECT session_id::text, role, text FROM or_turns ORDER BY session_id, created_at, id"
    )
    rows: dict[str, list[tuple[str, str]]] = {}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(query)
        for session_id, role, text in cur.fetchall():
            rows.setdefault(session_id, []).append((role, text))
    return {sid: turns for sid, turns in rows.items() if len(turns) >= min_turns}


def build_pairs(turns: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Fold a flat turn list into (learner, tutor) pairs, tolerating stray turns."""
    pairs: list[tuple[str, str]] = []
    pending: str | None = None
    for role, text in turns:
        if role == "user":
            if pending is not None:
                pairs.append((pending, ""))
            pending = text
        elif pending is not None:
            pairs.append((pending, text))
            pending = None
    if pending is not None:
        pairs.append((pending, ""))
    return pairs


def build_probes(
    sessions: dict[str, list[tuple[str, str]]], max_lookback: int
) -> list[Probe]:
    """One probe per learner turn that has at least one earlier exchange."""
    probes: list[Probe] = []
    for session_id, turns in sessions.items():
        pairs = build_pairs(turns)
        for index, (learner, _) in enumerate(pairs):
            if index == 0 or not learner.strip():
                continue
            start = max(0, index - max_lookback)
            probes.append(
                Probe(
                    session_id=session_id,
                    pair_index=index,
                    latest=learner,
                    context_pairs=pairs[start:index],
                )
            )
    return probes


def sample_evenly(probes: list[Probe], count: int) -> list[Probe]:
    """Take `count` probes spread across the whole set, not the first `count`.

    A prefix slice lands entirely inside the first session or two, which is how a
    smoke run ends up describing one conversation instead of the corpus. Striding
    keeps every session and every depth of conversation represented, and is
    deterministic so two partial runs stay comparable.
    """
    stride = len(probes) / count
    return [probes[int(i * stride)] for i in range(count)]


def render_prompt(probe: Probe) -> str:
    """Lay the history out labelled by distance, so the judge never has to count."""
    lines: list[str] = ["EARLIER EXCHANGES:", ""]
    total = len(probe.context_pairs)
    for offset, (learner, tutor) in enumerate(probe.context_pairs):
        back = total - offset
        lines.append(f"[-{back}] learner: {learner}")
        lines.append(f"[-{back}] tutor: {tutor}")
        lines.append("")
    lines.append("LATEST LEARNER MESSAGE:")
    lines.append(probe.latest)
    return "\n".join(lines)


def read_depth(body: dict) -> tuple[int, str]:
    """Take depth and reason out of the forced tool call.

    The fallback exists only for a gateway that strips tools on its way to a provider
    that has no equivalent: then the model answers in prose and the best we can do is
    find a number. A fallback hit is flagged in the CSV so it never passes as a real
    structured answer.
    """
    for block in body.get("content", []):
        if block.get("type") == "tool_use":
            payload = block.get("input", {})
            return int(payload["depth"]), str(payload.get("reason", ""))

    text = "".join(block.get("text", "") for block in body.get("content", []))
    found = re.search(r"\d+", text)
    if found is None:
        raise ValueError(f"judge returned no tool call and no number: {text[:120]!r}")
    return int(found.group()), "UNSTRUCTURED-FALLBACK"


async def judge(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    model: str,
    probe: Probe,
    max_lookback: int,
) -> Verdict:
    """Ask the judge for one probe's reference depth."""
    payload = {
        "model": model,
        "max_tokens": 256,
        "system": JUDGE_SYSTEM,
        "messages": [{"role": "user", "content": render_prompt(probe)}],
        "tools": [DEPTH_TOOL],
        "tool_choice": {"type": "tool", "name": DEPTH_TOOL["name"]},
    }
    async with semaphore:
        response = await client.post("/v1/messages", json=payload)
        if response.status_code >= 400:
            # The proxy explains refusals (bad key, unknown alias) in the body; the
            # bare status code alone sends you looking in the wrong place.
            raise RuntimeError(f"{response.status_code}: {response.text[:200]}")
        body = response.json()
    depth, reason = read_depth(body)
    depth = max(0, min(depth, max_lookback))
    return Verdict(
        session_id=probe.session_id,
        pair_index=probe.pair_index,
        depth=depth,
        clamped=depth == max_lookback and len(probe.context_pairs) >= max_lookback,
        reason=reason,
        latest=probe.latest,
    )


async def run_judges(
    probes: list[Probe], base_url: str, api_key: str, model: str,
    concurrency: int, max_lookback: int,
) -> list[Verdict]:
    """Judge every probe, reporting progress; a failed probe is skipped, not fatal."""
    semaphore = asyncio.Semaphore(concurrency)
    headers = {
        "x-api-key": api_key,
        "Authorization": f"Bearer {api_key}",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    verdicts: list[Verdict] = []
    async with httpx.AsyncClient(
        base_url=base_url, headers=headers, timeout=120.0
    ) as client:
        tasks = [
            judge(client, semaphore, model, probe, max_lookback) for probe in probes
        ]
        for done, task in enumerate(asyncio.as_completed(tasks), start=1):
            try:
                verdicts.append(await task)
            except Exception as exc:  # one bad probe must not lose the whole run
                print(f"  probe failed: {exc}", file=sys.stderr)
            if done % 25 == 0 or done == len(tasks):
                print(f"  judged {done}/{len(tasks)}", file=sys.stderr)
    return verdicts


def report(verdicts: list[Verdict], windows: list[int], max_lookback: int) -> None:
    """Print the histogram, the percentiles and the coverage table."""
    depths = [v.depth for v in verdicts]
    if not depths:
        print("no verdicts")
        return

    print(f"\nturns judged: {len(depths)}")
    print(f"sessions:     {len({v.session_id for v in verdicts})}")

    print("\nreference depth (pairs back needed)")
    histogram = Counter(depths)
    widest = max(histogram.values())
    for depth in range(0, max_lookback + 1):
        count = histogram.get(depth, 0)
        if count == 0:
            continue
        bar = "#" * max(1, round(count / widest * 40))
        label = f"{depth}+" if depth == max_lookback else str(depth)
        print(f"  {label:>4} {count:>5} ({count / len(depths) * 100:>5.1f}%) {bar}")

    ordered = sorted(depths)
    print("\npercentiles")
    for name, value in (
        ("p50", statistics.median(ordered)),
        ("p90", ordered[int(len(ordered) * 0.90)]),
        ("p95", ordered[int(len(ordered) * 0.95)]),
        ("p99", ordered[min(int(len(ordered) * 0.99), len(ordered) - 1)]),
        ("max", ordered[-1]),
    ):
        print(f"  {name}: {value}")

    print("\nwindow coverage -- share of turns a window of N pairs would have served")
    print(f"  {'window':>7} {'covered':>9} {'at risk':>9}")
    for window in windows:
        covered = sum(1 for d in depths if d <= window)
        share = covered / len(depths) * 100
        print(f"  {window:>7} {share:>8.1f}% {len(depths) - covered:>9}")

    clamped = sum(1 for v in verdicts if v.clamped)
    if clamped:
        print(
            f"\nnote: {clamped} turns hit the {max_lookback}-pair lookback limit; "
            "their true depth may be greater"
        )


def deepest_examples(verdicts: list[Verdict], count: int) -> None:
    """Show the turns that reach furthest back, so the judge can be spot-checked."""
    print(f"\ndeepest {count} turns (check the judge is not inventing dependencies)")
    for verdict in sorted(verdicts, key=lambda v: v.depth, reverse=True)[:count]:
        snippet = " ".join(verdict.latest.split())[:90]
        print(f"  depth={verdict.depth:>2} pair={verdict.pair_index:>3} "
              f"{verdict.reason[:40]:<40} | {snippet}")


def write_csv(verdicts: list[Verdict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["session_id", "pair_index", "depth", "clamped", "reason", "latest"])
        for v in sorted(verdicts, key=lambda v: (v.session_id, v.pair_index)):
            writer.writerow(
                [v.session_id, v.pair_index, v.depth, int(v.clamped), v.reason, v.latest]
            )
    print(f"\nwrote {path}")


def load_env_files() -> None:
    """Load the repository root .env, where this project keeps LLM_* and DB_*.

    Compose reads that one file and hands the values to every service, so the
    per-service .env files do not exist. Missing file and missing python-dotenv are
    both fine: anything not loaded here can still be passed on the command line.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    repo_root = Path(__file__).resolve().parents[3]
    for env_file in (
        repo_root / ".env",
        repo_root / "services" / "orchestrator-service" / ".env",
        repo_root / "services" / "llm-service" / ".env",
    ):
        if env_file.exists():
            load_dotenv(env_file, override=False)


def build_dsn() -> str:
    return (
        f"host={os.getenv('DB_HOST', 'localhost')} "
        f"port={os.getenv('DB_PORT', '5434')} "
        f"dbname={os.getenv('DB_DATABASE', 'orchestrator_service')} "
        f"user={os.getenv('DB_USERNAME', 'postgres')} "
        f"password={os.getenv('DB_PASSWORD', 'postgres')}"
    )


def main() -> None:
    load_env_files()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-turns", type=int, default=12,
                        help="skip sessions shorter than this many turns")
    parser.add_argument("--max-lookback", type=int, default=20,
                        help="how many pairs of history to show the judge")
    parser.add_argument("--limit", type=int, default=0,
                        help="judge at most this many turns (0 = all)")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--windows", default="3,4,6,8,12,16",
                        help="window sizes to report coverage for")
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", "tutor-default"))
    parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", "http://localhost:4000"))
    parser.add_argument("--api-key", default=os.getenv("LLM_API_KEY", ""))
    parser.add_argument("--out", default="reference_depth.csv")
    args = parser.parse_args()

    if not args.api_key:
        print(
            "LLM_API_KEY is empty: not found in the root .env and not passed as "
            "--api-key. Every call would come back 401.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    sessions = load_sessions(build_dsn(), args.min_turns)
    probes = build_probes(sessions, args.max_lookback)
    available = len(probes)
    if args.limit and args.limit < available:
        probes = sample_evenly(probes, args.limit)
    print(
        f"sessions: {len(sessions)}  turns available: {available}  "
        f"judging: {len(probes)}  model: {args.model}",
        file=sys.stderr,
    )
    if not probes:
        print("nothing to judge -- lower --min-turns", file=sys.stderr)
        return

    verdicts = asyncio.run(
        run_judges(probes, args.base_url, args.api_key, args.model,
                   args.concurrency, args.max_lookback)
    )
    windows = [int(w) for w in args.windows.split(",")]
    report(verdicts, windows, args.max_lookback)
    deepest_examples(verdicts, 10)
    write_csv(verdicts, args.out)


if __name__ == "__main__":
    main()
