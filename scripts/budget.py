"""Estimate calls, tokens and days per model for the full grid on Groq's free tier."""

import argparse
import math
import sys

from triage import defenses
from triage.models import model_id
from triage.run import load_reports

# Free-tier limits per model; check the account's limits page, they change.
REQUESTS_PER_DAY = 1_000
TOKENS_PER_DAY = 200_000
# Rough reply sizes: gpt-oss spends some reasoning tokens even at low effort.
JUDGE_OUTPUT_TOKENS = 300
EXTRACTOR_OUTPUT_TOKENS = 250
EXTRACTION_JSON_TOKENS = 250
# Stand-in length for real reports that have not been fetched yet (truncation cap).
UNFETCHED_REAL_CHARS = 2_500
REAL_COUNT = 25


def tokens(text_chars: int) -> int:
    """About four characters per token for English text."""
    return math.ceil(text_chars / 4)


def report_texts() -> list[str]:
    groups = load_reports(None)
    texts = [r.text for items in groups.values() for r in items]
    if not groups["real"]:
        print(
            f"note: data/real is empty; assuming {REAL_COUNT} real reports of "
            f"{UNFETCHED_REAL_CHARS} chars each"
        )
        texts += ["x" * UNFETCHED_REAL_CHARS] * REAL_COUNT
    return texts


def plan(texts: list[str], judges: list[str]) -> dict[str, tuple[int, int]]:
    """Calls and tokens per model; extractor and guard calls are shared by both judges."""
    system = tokens(len(defenses.JUDGE_SYSTEM))
    per_judge_calls = per_judge_tokens = 0
    extractor_tokens = guard_calls = guard_tokens = 0
    for text in texts:
        report = tokens(len(text))
        spotlit = tokens(len(defenses.SPOTLIGHT_NOTE) + len(defenses.datamark(text)) + 30)
        quarantined = tokens(len(defenses.QUARANTINE_NOTE)) + EXTRACTION_JSON_TOKENS
        per_judge_calls += 3
        per_judge_tokens += 3 * (system + JUDGE_OUTPUT_TOKENS) + report + spotlit + quarantined
        extractor_tokens += tokens(len(defenses.EXTRACTOR_SYSTEM)) + report
        extractor_tokens += EXTRACTOR_OUTPUT_TOKENS
        pieces = defenses.chunk(text)
        guard_calls += len(pieces)
        guard_tokens += sum(tokens(len(piece)) + 2 for piece in pieces)
    result = {name: (per_judge_calls, per_judge_tokens) for name in judges}
    result[model_id("EXTRACTOR_MODEL")] = (len(texts), extractor_tokens)
    result[model_id("GUARD_MODEL")] = (guard_calls, guard_tokens)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="a,b", help="judges: a (large), b (small)")
    args = parser.parse_args(argv)
    judges = [model_id(f"JUDGE_{key.upper()}_MODEL") for key in args.models.split(",")]
    texts = report_texts()
    print(f"{len(texts)} reports; 4 defenses (guard reuses baseline verdicts)")
    print(
        f"limits assumed per model: {REQUESTS_PER_DAY:,} requests/day, "
        f"{TOKENS_PER_DAY:,} tokens/day"
    )
    print(f"{'model':<40} {'calls':>7} {'est. tokens':>12} {'days':>6}")
    longest = 0.0
    for name, (calls, total) in sorted(plan(texts, judges).items()):
        days = max(calls / REQUESTS_PER_DAY, total / TOKENS_PER_DAY)
        longest = max(longest, days)
        print(f"{name:<40} {calls:>7,} {total:>12,} {days:>6.1f}")
    print(
        f"models run on separate quotas, so the full grid needs about "
        f"{math.ceil(longest)} days; parse retries add a little"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
