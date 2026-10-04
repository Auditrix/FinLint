"""Tests for the six checks, one per fixture.

Each fixture carries exactly one deliberate problem, so the expected answer is
known in advance. Coordinates are compared, never whole Finding objects, so a
reworded message never breaks a test.
"""

from finlint.parsing.reader import read_workbook
from finlint.graph.build import build_graph
from finlint.rules.checks import check_error_cells, check_circular,check_hardcoded_value,check_broken_links,check_formula_drift,check_dead_inputs,ALL_CHECKS

def load(name):
    """Read a fixture and build its dependency map."""
    workbook = read_workbook("tests/fixtures/%s.xlsx" % name)
    return workbook, build_graph(workbook)

def test_error_cells():
    """The #REF! left in Summary!A3."""
    wb,graph=load("brokenlink")
    findings=check_error_cells(wb,graph)
    assert [f.coordinate for f in findings]==["A3"]
    
def test_circular():
    """Both loops, and nothing else. E1 and E2 are clean and must not appear."""
    wb,graph=load("circular")
    findings=check_circular(wb,graph)
    assert sorted([f.coordinate for f in findings])==["A1", "A2", "C1", "C2", "C3"]
    
def test_hardcoded_value():
    """C15 was typed in where B15 and D15 are calculated."""
    wb,graph=load("hardcode")
    findings=check_hardcoded_value(wb,graph)
    assert [f.coordinate for f in findings]==["C15"]
    
def test_broken_links():
    """One missing sheet and one missing workbook."""
    wb,graph=load("brokenlink")
    findings=check_broken_links(wb,graph)
    assert sorted([f.coordinate for f in findings])==["A1", "A2"]
    
def test_formula_drift():
    """D15 forgot to subtract, so its shape differs from the rest of its row."""
    wb,graph=load("drift")
    findings=check_formula_drift(wb,graph)
    assert[f.coordinate for f in findings]==["D15"]
    
def test_dead_inputs():
    """Three typed numbers that no formula reads. C15 being typed orphaned C12 and C13."""
    wb,graph=load("hardcode")
    findings=check_dead_inputs(wb,graph)
    assert sorted([f.coordinate for f in findings])==["C12","C13","C15"]
    
def test_clean_workbooks_produce_nothing():
    """The most valuable test here: no check may invent a finding or crash
    on a workbook that has nothing wrong with it."""
    for name in ("merged","arrayformula"):
        wb,graph=load(name)
        for check in ALL_CHECKS:
            findings=check(wb,graph)
            assert findings==[]
    
    