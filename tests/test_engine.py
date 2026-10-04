"""Tests for engine.py.

The checks themselves are covered in test_checks.py, so these only cover what
the engine adds: running every check, and the order it puts them in.
"""

from finlint.rules.engine import check_workbook
from finlint.rules.model import SEVERITY_ORDER, Finding


def test_runs_every_check():
    """One call must gather findings from more than one check."""
    findings = check_workbook("tests/fixtures/brokenlink.xlsx")
    assert len(findings) == 4
    assert {f.rule_id for f in findings} == {"error_cells", "broken_link", "dead_input"}


def test_sorted_worst_first():
    """Severity decides the order: critical, then high, then medium, then low."""
    findings = check_workbook("tests/fixtures/brokenlink.xlsx")
    assert [f.severity for f in findings] == ["high", "medium", "medium", "low"]


def test_bigger_blast_radius_comes_first():
    """Within one severity, the finding that breaks more cells is ranked higher.

    The fixtures cannot show this, because every blast radius in them is 0,
    so the two findings are built by hand here.
    """
    small = Finding(rule_id="r", severity="high", sheet="S", coordinate="A1",
                    message="breaks little", blast_radius=2)
    large = Finding(rule_id="r", severity="high", sheet="S", coordinate="A2",
                    message="breaks a lot", blast_radius=90)

    ordered = sorted([small, large],
                     key=lambda f: (SEVERITY_ORDER.index(f.severity), -f.blast_radius))

    assert [f.coordinate for f in ordered] == ["A2", "A1"]
