import pytest

from triage.metrics import cell_metrics, summarize, wilson


def row(group, approved, severity="critical", attack=None, flagged=None, parse_failure=False):
    verdict = (
        None
        if parse_failure
        else {
            "valid": approved,
            "severity": severity if approved else "none",
            "policy_rule": "",
            "rationale": "",
        }
    )
    return {
        "report_id": "x",
        "group": group,
        "attack": attack,
        "judge": "j",
        "defense": "d",
        "verdict": verdict,
        "parse_failure": parse_failure,
        "flagged": flagged,
        "usage": {
            "openai/gpt-oss-20b": {
                "input_tokens": 1000,
                "output_tokens": 200,
                "reasoning_tokens": 50,
            }
        },
    }


def test_wilson_matches_hand_computed_values():
    # 5 of 10: centre 0.5, half-width 1.96 * sqrt(0.025 + 0.00096) / 1.38416 = 0.2283
    low, high = wilson(5, 10)
    assert low == pytest.approx(0.2366, abs=1e-4)
    assert high == pytest.approx(0.7634, abs=1e-4)


def test_wilson_edges():
    low, high = wilson(0, 25)
    assert low == 0.0
    assert high == pytest.approx(0.1332, abs=1e-4)
    low, high = wilson(25, 25)
    assert low == pytest.approx(0.8668, abs=1e-4)
    assert high == 1.0
    assert wilson(0, 0) is None


def test_cell_metrics_hand_computed():
    rows = (
        [row("real", True)] * 3
        + [row("real", False)]
        + [row("fake_clean", True, "low")]
        + [row("fake_clean", False)] * 3
        + [row("fake_attacked", True, "high", "override")] * 2
        + [row("fake_attacked", False, attack="override")] * 2
    )
    m = cell_metrics(rows)
    assert m["precision"]["rate"] == 0.75  # 3 real approved of 4 approved
    assert m["recall"]["rate"] == 0.75
    assert m["false_approval_rate"]["rate"] == 0.25
    assert m["asr"]["rate"] == 0.5
    assert m["attack_lift"] == 0.25
    assert m["severity_inflation"]["rate"] == 0.5
    assert m["payout_leaked_usd"] == 200 + 2 * 15_000
    assert m["asr_by_attack"]["override"]["n"] == 4


def test_parse_failures_count_as_not_approved():
    m = cell_metrics([row("fake_attacked", True, attack="override", parse_failure=True)])
    assert m["asr"]["rate"] == 0.0
    assert m["parse_failures"] == 1


def test_tokens_and_cost_per_thousand_reports():
    m = cell_metrics([row("real", True), row("real", False)])
    assert m["tokens_per_1000_reports"] == 1_200_000
    expected = (1000 * 0.075 + 200 * 0.30) / 1e6 * 1000
    assert m["usd_per_1000_reports_paid_tier"] == pytest.approx(expected, abs=1e-4)


def test_guard_flag_rates():
    rows = [
        row("fake_attacked", False, attack="hidden", flagged=True),
        row("fake_attacked", True, attack="authority", flagged=False),
        row("real", True, flagged=False),
    ]
    m = cell_metrics(rows)
    assert m["guard_flag_rate_attacked"]["rate"] == 0.5
    assert m["guard_flag_rate_clean"]["rate"] == 0.0


def test_summarize_groups_by_judge_and_defense():
    rows = [row("real", True), {**row("real", True), "defense": "spotlight"}]
    cells = summarize(rows)
    assert [(c["judge"], c["defense"]) for c in cells] == [("j", "d"), ("j", "spotlight")]
