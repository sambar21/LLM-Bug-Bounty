"""Print resume bullets filled from a real run; rewrite any bullet the data contradicts."""

import json
import math
import sys
from pathlib import Path

from triage.models import model_id

SUMMARY = Path(__file__).resolve().parent.parent / "results" / "summary.json"


def floor_pct(value: float) -> int:
    return math.floor(value * 100)


def ceil_pct(value: float) -> int:
    return math.ceil(value * 100)


def load_cells() -> dict[tuple[str, str], dict]:
    if not SUMMARY.exists():
        raise SystemExit(f"{SUMMARY} not found; run `make bench` and `make report` first")
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    if summary.get("mock") or summary.get("label") == "MOCK":
        raise SystemExit("refusing to write resume bullets from MOCK results")
    return {(c["judge"], c["defense"]): c for c in summary["cells"]}


def need(cells: dict, judge: str, defense: str) -> dict:
    if (judge, defense) not in cells:
        raise SystemExit(f"no results for {judge} / {defense}; finish the grid first")
    return cells[(judge, defense)]


def rate(cell: dict, key: str) -> float:
    value = cell[key]["rate"]
    if value is None:
        raise SystemExit(f"{key} is undefined for {cell['judge']} / {cell['defense']}")
    return value


def bullets(cells: dict, large: str, small: str) -> list[str]:
    base = need(cells, large, "baseline")
    quar = need(cells, large, "quarantine")
    guard = need(cells, large, "guard")
    small_base = need(cells, small, "baseline")
    precision = rate(base, "precision")
    asr_base, asr_q, asr_guard = rate(base, "asr"), rate(quar, "asr"), rate(guard, "asr")
    leak = math.floor(base["payout_leaked_usd"] / 1000) * 1000
    lines = [
        f"Built an LLM bug bounty triager scoring {floor_pct(precision)}% precision on 50 "
        "hand-labeled reports (25 real HackerOne disclosures, 25 fakes).",
        "Red-teamed it with 5 prompt injection techniques hidden in 125 fake reports; "
        f"{floor_pct(asr_base)}% were approved as valid, worth ${leak:,} under a sample "
        "payout table.",
        defense_bullet(base, quar, asr_base, asr_q, asr_guard, guard),
        size_bullet(asr_base, rate(small_base, "asr")),
    ]
    return lines


def defense_bullet(base, quar, asr_base, asr_q, asr_guard, guard) -> str:
    caught = floor_pct(guard["guard_flag_rate_attacked"]["rate"])
    delta = (rate(base, "precision") - rate(quar, "precision")) * 100
    if asr_q >= asr_base:
        return (f"Tested splitting extraction from judgment; it did not reduce prompt injection "
                f"success ({floor_pct(asr_base)}% before, {ceil_pct(asr_q)}% after). An "
                f"off-the-shelf injection classifier caught {caught}% of attacks.")
    cost = (f"at a cost of {math.ceil(delta)} points of precision" if delta > 0
            else "with no loss of precision")
    line = (f"Cut prompt injection success from {floor_pct(asr_base)}% to {ceil_pct(asr_q)}% "
            f"by splitting extraction from judgment, {cost}; an off-the-shelf injection "
            f"classifier caught {caught}% of attacks.")
    if asr_guard < asr_q:
        line += (f" The classifier did better on its own, leaving {ceil_pct(asr_guard)}% "
                 "of attacks approved.")
    return line


def size_bullet(asr_large: float, asr_small: float) -> str:
    tail = "released the 125-report attack set as a one-command benchmark."
    if asr_large == 0 or asr_small <= asr_large:
        return (f"Found the 20B model no easier to hijack than the 120B model "
                f"({floor_pct(asr_small)}% vs {floor_pct(asr_large)}% approved); {tail}")
    ratio = math.floor(asr_small / asr_large * 10) / 10
    if ratio < 1.1:
        return (f"Found the 20B and 120B models about equally easy to hijack "
                f"({floor_pct(asr_small)}% vs {floor_pct(asr_large)}% approved); {tail}")
    return f"Found the 20B model {ratio}x easier to hijack than the 120B model; {tail}"


def main() -> int:
    cells = load_cells()
    for line in bullets(cells, model_id("JUDGE_A_MODEL"), model_id("JUDGE_B_MODEL")):
        print(f"- {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
