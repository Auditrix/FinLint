from finlint.parsing.reader import read_workbook
from finlint.graph.build import build_graph
from finlint.rules.checks import check_error_cells, check_circular,check_hardcoded_value,check_broken_links,check_formula_drift,check_dead_inputs,ALL_CHECKS

def load(name):
    """Read a fixture and build its dependency map."""
    workbook = read_workbook("tests/fixtures/%s.xlsx" % name)
    return workbook, build_graph(workbook)

def test_error_cells():
    wb,graph=load("brokenlink")
    findings=check_error_cells(wb,graph)
    assert [f.coordinate for f in findings]==["A3"]
    
def test_circular():
    wb,graph=load("circular")
    findings=check_circular(wb,graph)
    assert sorted([f.coordinate for f in findings])==["A1", "A2", "C1", "C2", "C3"]
    
def test_hardcoded_value():
    wb,graph=load("hardcode")
    findings=check_hardcoded_value(wb,graph)
    assert [f.coordinate for f in findings]==["C15"]
    
def test_broken_links():
    wb,graph=load("brokenlink")
    findings=check_broken_links(wb,graph)
    assert sorted([f.coordinate for f in findings])==["A1", "A2"]
    
def test_formula_drift():
    wb,graph=load("drift")
    findings=check_formula_drift(wb,graph)
    assert[f.coordinate for f in findings]==["D15"]
    
def test_dead_inputs():
    wb,graph=load("hardcode")
    findings=check_dead_inputs(wb,graph)
    assert sorted([f.coordinate for f in findings])==["C12","C13","C15"]
    
def test_clean_workbooks_produce_nothing():
    for name in ("merged","arrayformula"):
        wb,graph=load(name)
        for check in ALL_CHECKS:
            findings=check(wb,graph)
            assert findings==[]
    
    