import json

from finlint.eval.score import (
    cell_id,
    load_excelint_annotations,
    precision_recall,
    resolve_excelint_workbook,
    score_findings,
    tier_one_expected,
)
from finlint.rules.model import Finding


def finding(rule_id, sheet, coordinate):
    return Finding(
        rule_id=rule_id,
        severity="high",
        sheet=sheet,
        coordinate=coordinate,
        message="test finding",
    )


def test_precision_recall_counts_each_result():
    expected = {"A", "B"}
    predicted = {"B", "C"}

    result = precision_recall(expected, predicted)

    assert result["true_positives"] == 1
    assert result["false_positives"] == 1
    assert result["false_negatives"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5


def test_score_findings_reports_each_rule():
    expected = {
        cell_id("book.xlsx", "Sheet1", "A1"),
        cell_id("book.xlsx", "Sheet1", "A2"),
    }
    findings = {
        "book.xlsx": [
            finding("error_cells", "Sheet1", "A1"),
            finding("broken_link", "Sheet1", "B1"),
        ]
    }

    result = score_findings(expected, findings)

    assert result["overall"]["precision"] == 0.5
    assert result["overall"]["recall"] == 0.5
    assert result["by_rule"]["error_cells"]["true_positives"] == 1
    assert result["by_rule"]["broken_link"]["false_positives"] == 1


def test_load_excelint_annotations_uses_column_then_row(tmp_path):
    path = tmp_path / "annotations.json"
    path.write_text(
        json.dumps({"book.xlsx": {"Data": {"bugs": [[11, 35, 0]]}}}),
        encoding="utf-8",
    )

    expected = load_excelint_annotations(path)

    assert expected == {cell_id("book.xlsx", "Data", "K35")}


def test_encoded_excelint_name_matches_downloaded_name(tmp_path):
    workbook = tmp_path / "My_20File.xlsx"
    workbook.touch()
    assert resolve_excelint_workbook(tmp_path, "My%20File.xlsx") == workbook


def test_truncated_excelint_name_matches_downloaded_name(tmp_path):
    workbook = tmp_path / "Report_2#A123.xlsx"
    workbook.touch()
    assert resolve_excelint_workbook(tmp_path, "Report%2#A123.xlsx") == workbook


def test_tier_one_keeps_repeated_faults_separate():
    records = [
        {"fault_id": 1, "sheet": "Calc", "coordinate": "A3"},
        {"fault_id": 2, "sheet": "Calc", "coordinate": "A3"},
    ]
    assert tier_one_expected(records) == {
        cell_id("1", "Calc", "A3"),
        cell_id("2", "Calc", "A3"),
    }
