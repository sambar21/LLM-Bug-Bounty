"""Write results/summary.json, results/heatmap.png and results/table.md."""

import argparse
import json
import sys
from pathlib import Path

from triage.attacks import ATTACKS
from triage.defenses import keyword_baseline
from triage.metrics import cross_check_rows, summarize
from triage.run import DEFENSE_ORDER, ROOT, load_reports, outcome_row

KEYWORD_JUDGE = "keyword-baseline"

SMALL_N_NOTE = (
    "n is small (25 real, 25 fake, 25 per attack); read the 95% Wilson intervals, "
    "not just the point estimates."
)


def load_rows(out_dir: Path) -> list[dict]:
    path = out_dir / "outcomes.jsonl"
    if not path.exists():
        raise SystemExit(f"{path} not found; run the bench first")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def pct(cell: dict | None) -> str:
    if not cell or cell["rate"] is None:
        return "-"
    low, high = cell["ci95"]
    return f"{cell['rate'] * 100:.0f}% ({low * 100:.0f}-{high * 100:.0f})"


def write_table(cells: list[dict], path: Path, mock: bool) -> None:
    lines = [
        "| Judge | Defense | Precision | Recall | False approval | ASR | Lift | "
        "High/crit on attacked | Payout leaked | To human | Tokens / 1k reports | Sec / report |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in cells:
        lift = "-" if c["attack_lift"] is None else f"{c['attack_lift'] * 100:+.0f} pts"
        timed = c["seconds_per_report"]
        seconds = "-" if timed is None else f"{timed['mean']:.1f}"
        lines.append(
            f"| {c['judge']} | {c['defense']} | {pct(c['precision'])} | {pct(c['recall'])} | "
            f"{pct(c['false_approval_rate'])} | {pct(c['asr'])} | {lift} | "
            f"{pct(c['severity_inflation'])} | ${c['payout_leaked_usd']:,} | "
            f"{pct(c['human_review_rate'])} | {c['tokens_per_1000_reports']:,} | {seconds} |"
        )
    header = "MOCK RESULTS: offline mock model, not a real measurement.\n\n" if mock else ""
    footer = (
        f"\nRates with 95% Wilson intervals in brackets. {SMALL_N_NOTE} "
        "cross-check approves only when both judges approve; disagreements go to a human. "
        "Sec / report counts only API calls that were timed.\n"
    )
    path.write_text(header + "\n".join(lines) + "\n" + footer, encoding="utf-8")


def write_heatmap(cells: list[dict], path: Path, mock: bool) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # The keyword baseline has one column, so it lives in the table, not the heatmap.
    judges = sorted({c["judge"] for c in cells} - {KEYWORD_JUDGE})
    attacks = sorted(ATTACKS)
    figure, axes = plt.subplots(1, len(judges), figsize=(6 * len(judges), 4.4), squeeze=False)
    for axis, judge in zip(axes[0], judges, strict=True):
        by_defense = {c["defense"]: c["asr_by_attack"] for c in cells if c["judge"] == judge}
        grid = [[_attack_rate(by_defense, d, a) for d in DEFENSE_ORDER] for a in attacks]
        values = [[v if v is not None else float("nan") for v in row] for row in grid]
        axis.imshow(values, cmap="Reds", vmin=0, vmax=100)
        for i, row in enumerate(grid):
            for j, value in enumerate(row):
                label = "-" if value is None else f"{value:.0f}%"
                colour = "white" if value is not None and value > 60 else "black"
                axis.text(j, i, label, ha="center", va="center", color=colour)
        axis.set_xticks(range(len(DEFENSE_ORDER)), DEFENSE_ORDER, rotation=25, ha="right")
        axis.set_yticks(range(len(attacks)), attacks)
        axis.set_title(judge)
    title = "Attack success rate (% of attacked fakes approved)"
    figure.suptitle(f"MOCK - {title}" if mock else title)
    figure.tight_layout()
    figure.savefig(path, dpi=120)
    plt.close(figure)


def _attack_rate(by_defense: dict, defense: str, attack: str) -> float | None:
    cell = by_defense.get(defense, {}).get(attack)
    return None if cell is None or cell["rate"] is None else cell["rate"] * 100


def derived_rows(rows: list[dict], mock: bool) -> list[dict]:
    """Rows needing no new model calls: the keyword baseline and the two-judge cross-check."""
    reports = [r for items in load_reports(None).values() for r in items]
    keyword = [
        outcome_row(r, "keyword", KEYWORD_JUDGE, keyword_baseline(r.text), mock) for r in reports
    ]
    judges = sorted({row["judge"] for row in rows})
    cross = cross_check_rows(rows, (judges[0], judges[1])) if len(judges) == 2 else []
    return keyword + cross


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", help="report on results/mock")
    args = parser.parse_args(argv)
    out_dir = ROOT / "results" / ("mock" if args.mock else "")
    rows = load_rows(out_dir)
    mock = any(row["mock"] for row in rows)
    if mock != args.mock:
        raise SystemExit("outcomes do not match the requested mode; refusing to mix MOCK and real")
    cells = summarize(rows + derived_rows(rows, mock))
    summary = {
        "mock": mock,
        "label": "MOCK" if mock else "real",
        "rows": len(rows),
        "note": SMALL_N_NOTE,
        "cells": cells,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_table(cells, out_dir / "table.md", mock)
    write_heatmap(cells, out_dir / "heatmap.png", mock)
    print(f"wrote summary.json, table.md and heatmap.png to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
