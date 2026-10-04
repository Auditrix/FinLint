"""Run every check over one workbook and rank what comes back.

This is the single door into the rule engine. Anything that wants findings,
the evaluation code, the dashboard, a future API, calls check_workbook and
gets one ordered list.
"""

from finlint.graph.build import build_graph
from finlint.parsing.reader import read_workbook
from finlint.rules.checks import ALL_CHECKS
from finlint.rules.model import Finding, SEVERITY_ORDER


def run_all(workbook, graph) -> list[Finding]:
    """Run all six checks and return their findings, worst first, one per cell.

    Two rules can both fire on the same cell, and one cell can hold several
    broken references. Only the most serious finding for a cell is kept, so a
    count of findings is always a count of cells and precision cannot be
    distorted by the same cell being reported twice.
    """
    findings = []
    for check in ALL_CHECKS:
        findings += check(workbook, graph)

    # Two keys, read as a pair. Severity decides first, because critical must
    # come before high. Within one severity the finding that breaks the most
    # cells comes first, and the minus sign turns "biggest" into "first".
    findings.sort(key=lambda f: (SEVERITY_ORDER.index(f.severity), -f.blast_radius))

    # Sorted worst first, so the first finding seen for a cell is the one to keep.
    best = {}
    for finding in findings:
        best.setdefault((finding.sheet, finding.coordinate), finding)
    return list(best.values())


def check_workbook(path) -> list[Finding]:
    """Read a workbook from disk, map it, check it, and return the ranked findings."""
    workbook = read_workbook(path)
    graph = build_graph(workbook)
    return run_all(workbook, graph)
