"""Check that batch counts are combined before precision and recall are calculated."""

from scripts.run_tier_one import combine_reports


def test_combine_reports_uses_all_faults():
    first = {
        "overall": {"true_positives": 1, "false_positives": 2},
        "by_rule": {"formula_drift": {"true_positives": 1, "false_positives": 2}},
        "baseline_findings": {"seed.xlsx": 5},
    }
    second = {
        "overall": {"true_positives": 0, "false_positives": 1},
        "by_rule": {"formula_drift": {"true_positives": 0, "false_positives": 1}},
        "baseline_findings": {"seed.xlsx": 5},
    }

    result = combine_reports([first, second], total_faults=2)

    assert result["overall"]["true_positives"] == 1
    assert result["overall"]["false_positives"] == 3
    assert result["overall"]["false_negatives"] == 1
    assert result["overall"]["precision"] == 0.25
    assert result["overall"]["recall"] == 0.5
    assert result["by_rule"]["formula_drift"]["false_positives"] == 3
