"""Calculate precision and recall for planted faults and ExcelInt."""

import json
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl.utils import get_column_letter

from finlint.eval.faults import write_mutated_copy
from finlint.graph.build import build_graph
from finlint.parsing.reader import read_workbook


def cell_id(workbook: str, sheet: str, coordinate: str) -> tuple[str, str, str]:
    """Build a case-insensitive identity for one workbook cell."""
    return workbook.casefold(), sheet.casefold(), coordinate.upper()


def precision_recall(expected: set, predicted: set) -> dict:
    """Calculate the standard cell-level classification scores."""
    true_positives = len(expected & predicted)
    false_positives = len(predicted - expected)
    false_negatives = len(expected - predicted)

    precision = true_positives / len(predicted) if predicted else 0.0
    recall = true_positives / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def score_findings(expected: set, findings_by_workbook: dict[str, list]) -> dict:
    """Score all findings together and also show what each rule caught."""
    all_predicted = set()
    predicted_by_rule = defaultdict(set)

    for workbook_name, findings in findings_by_workbook.items():
        for finding in findings:
            found_cell = cell_id(workbook_name, finding.sheet, finding.coordinate)
            all_predicted.add(found_cell)
            predicted_by_rule[finding.rule_id].add(found_cell)

    by_rule = {
        rule_id: precision_recall(expected, predicted)
        for rule_id, predicted in sorted(predicted_by_rule.items())
    }
    return {
        "overall": precision_recall(expected, all_predicted),
        "by_rule": by_rule,
    }


def load_excelint_annotations(path: str | Path) -> set[tuple[str, str, str]]:
    """Read ExcelInt's [column, row, group] entries as workbook cell identities."""
    with Path(path).open(encoding="utf-8") as file:
        annotations = json.load(file)

    expected = set()
    for workbook_name, sheets in annotations.items():
        for sheet_name, details in sheets.items():
            for column, row, _group in details.get("bugs", []):
                coordinate = f"{get_column_letter(column)}{row}"
                expected.add(cell_id(workbook_name, sheet_name, coordinate))
    return expected


def resolve_excelint_workbook(folder: str | Path, annotation_name: str) -> Path:
    """Match encoded ExcelInt names to the names used in the downloaded folder."""
    folder = Path(folder)
    direct_path = folder / annotation_name
    if direct_path.exists():
        return direct_path

    drive_name = annotation_name.replace("%20", "_20").replace("%", "_")
    drive_path = folder / drive_name
    if drive_path.exists():
        return drive_path

    raise FileNotFoundError(f"ExcelInt workbook not found: {annotation_name}")


def tier_one_expected(records: list[dict]) -> set[tuple[str, str, str]]:
    """Use the injected cell as the one expected finding for each mutation."""
    return {
        cell_id(str(record["fault_id"]), record["sheet"], record["coordinate"])
        for record in records
    }


def evaluate_tier_one(records: list[dict], run_engine) -> dict:
    """Recreate each planted fault, run the engine, and score its findings."""
    findings_by_fault = {}

    for record in records:
        source_path = Path(record["source_path"])
        with TemporaryDirectory() as temporary_folder:
            mutated_path = Path(temporary_folder) / source_path.name
            write_mutated_copy(
                source_path,
                mutated_path,
                record["sheet"],
                record["coordinate"],
                record.get("mutated_formula"),
            )
            workbook = read_workbook(mutated_path)
            graph = build_graph(workbook)
            findings_by_fault[str(record["fault_id"])] = run_engine(workbook, graph)

    return score_findings(tier_one_expected(records), findings_by_fault)


def evaluate_tier_two(
    benchmark_folder: str | Path,
    annotation_path: str | Path,
    run_engine,
) -> dict:
    """Run the unchanged engine over every ExcelInt workbook."""
    with Path(annotation_path).open(encoding="utf-8") as file:
        annotation_data = json.load(file)

    findings_by_workbook = {}
    errors = []

    for annotation_name in annotation_data:
        try:
            workbook_path = resolve_excelint_workbook(benchmark_folder, annotation_name)
            workbook = read_workbook(workbook_path)
            graph = build_graph(workbook)
            findings_by_workbook[annotation_name] = run_engine(workbook, graph)
        except Exception as error:
            errors.append({"workbook": annotation_name, "error": str(error)})

    report = score_findings(
        load_excelint_annotations(annotation_path),
        findings_by_workbook,
    )
    report["workbooks_processed"] = len(findings_by_workbook)
    report["errors"] = errors
    return report


def save_report(path: str | Path, report: dict) -> None:
    """Save an evaluation report as readable JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
