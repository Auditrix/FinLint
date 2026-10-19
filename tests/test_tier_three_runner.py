"""Check that Tier 3 counts workbooks, not findings, and never hides a crash.

Tier 3 has no answer key, so the only numbers it produces are the trigger rate
and the per rule counts. Both are easy to get subtly wrong, in two ways this
file pins down:

  1. One noisy workbook with 80 hardcodes must count ONCE towards that rule,
     otherwise a single bad file makes a rule look universal.
  2. A workbook that failed to open must never be counted as a clean workbook,
     or the trigger rate quietly improves every time the parser breaks.
"""

from pathlib import Path

from scripts.run_tier_three import summarise, workbook_id


ARENA = Path("data/benchmarks/arena")


def finding(rule_id, severity="high", sheet="Sheet1", coordinate="A1"):
    return {
        "rule_id": rule_id,
        "severity": severity,
        "sheet": sheet,
        "coordinate": coordinate,
        "message": "test finding",
        "blast_radius": 0,
    }


def test_rule_counts_are_per_workbook_not_per_finding():
    """Three hardcodes in one workbook is one workbook, not three."""
    results = [
        {
            "path": str(ARENA / "outputs" / "aaa" / "sheet.xlsx"),
            "error": None,
            "findings": [
                finding("hardcoded_value", coordinate="A1"),
                finding("hardcoded_value", coordinate="A2"),
                finding("hardcoded_value", coordinate="A3"),
            ],
        },
    ]

    report = summarise(results, ARENA)

    assert report["workbooks_per_rule"]["hardcoded_value"] == 1
    assert report["findings_per_rule"]["hardcoded_value"] == 3


def test_failed_workbooks_are_excluded_from_the_trigger_rate():
    """A workbook that would not open is not evidence that the file was clean."""
    results = [
        {"path": str(ARENA / "outputs" / "aaa" / "sheet.xlsx"), "error": None,
         "findings": [finding("dead_input")]},
        {"path": str(ARENA / "outputs" / "bbb" / "sheet.xlsx"), "error": None,
         "findings": []},
        {"path": str(ARENA / "outputs" / "ccc" / "sheet.xlsx"), "error": "ValueError",
         "findings": []},
    ]

    report = summarise(results, ARENA)

    assert report["workbooks_found"] == 3
    assert report["workbooks_scanned"] == 2      # the crash is not a scan
    assert report["workbooks_failed"] == 1
    assert report["failure_types"] == {"ValueError": 1}
    # One of the two readable workbooks triggered, so the rate is a half.
    assert report["trigger_rate"] == 0.5


def test_empty_run_does_not_divide_by_zero():
    """Every workbook failing is a real outcome, not a crash in the report."""
    results = [
        {"path": str(ARENA / "outputs" / "aaa" / "sheet.xlsx"), "error": "KeyError",
         "findings": []},
    ]

    report = summarise(results, ARENA)

    assert report["workbooks_scanned"] == 0
    assert report["trigger_rate"] == 0.0
    assert report["findings_per_workbook"]["mean"] == 0.0


def test_workbook_id_uses_the_arena_hash_folder():
    """Arena stores every file as outputs/<hash>/sheet.xlsx, so "sheet" is useless."""
    path = ARENA / "outputs" / "09a8befd9ab084c9" / "sheet.xlsx"

    assert workbook_id(path, ARENA) == "09a8befd9ab084c9"
