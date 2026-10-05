import pytest

from finlint.graph.graph import Graph
from finlint.parsing.model import Cell, Sheet, Workbook

checks = pytest.importorskip("finlint.rules.checks")


def make_workbook(cells):
    sheet = Sheet(name="S", state="visible", cells={cell.coordinate: cell for cell in cells})
    return Workbook(path="test.xlsx", sheets={"S": sheet})


def coordinates(findings):
    return {(finding.sheet, finding.coordinate) for finding in findings}


def test_error_cells_does_not_report_clean_values():
    workbook = make_workbook(
        [
            Cell(sheet="S", coordinate="A1", data_type="e", number_format="General", cached_value="#DIV/0!"),
            Cell(sheet="S", coordinate="A2", data_type="n", number_format="General", cached_value=10),
        ]
    )
    assert coordinates(checks.check_error_cells(workbook, Graph())) == {("S", "A1")}


def test_circular_refs_returns_only_cycle_cells():
    graph = Graph(
        feeds_into={
            "S!A1": {"S!A2"},
            "S!A2": {"S!A1"},
            "S!B1": {"S!B2"},
            "S!B2": set(),
        }
    )
    assert coordinates(checks.check_circular(make_workbook([]), graph)) == {
        ("S", "A1"),
        ("S", "A2"),
    }


def test_dead_input_returns_unused_number_only():
    workbook = make_workbook(
        [
            Cell(sheet="S", coordinate="A1", data_type="n", number_format="General", cached_value=10),
            Cell(sheet="S", coordinate="A2", data_type="n", number_format="General", cached_value=20),
            Cell(sheet="S", coordinate="B1", data_type="f", number_format="General", formula="=A1*2"),
        ]
    )
    graph = Graph(
        feeds={"S!B1": {"S!A1"}},
        feeds_into={"S!A1": {"S!B1"}},
    )
    assert coordinates(checks.check_dead_inputs(workbook, graph)) == {("S", "A2")}


def test_hardcoded_value_finds_number_between_formulas():
    workbook = make_workbook(
        [
            Cell(sheet="S", coordinate="B3", data_type="f", number_format="General", formula="=B1-B2"),
            Cell(sheet="S", coordinate="C3", data_type="n", number_format="General", cached_value=72),
            Cell(sheet="S", coordinate="D3", data_type="f", number_format="General", formula="=D1-D2"),
        ]
    )
    assert coordinates(checks.check_hardcoded_value(workbook, Graph())) == {("S", "C3")}


def test_formula_drift_finds_the_different_formula():
    workbook = make_workbook(
        [
            Cell(sheet="S", coordinate="B3", data_type="f", number_format="General", formula="=B1-B2"),
            Cell(sheet="S", coordinate="C3", data_type="f", number_format="General", formula="=C1+C2"),
            Cell(sheet="S", coordinate="D3", data_type="f", number_format="General", formula="=D1-D2"),
        ]
    )
    assert coordinates(checks.check_formula_drift(workbook, Graph())) == {("S", "C3")}


def test_broken_link_finds_missing_sheet_and_external_file():
    workbook = make_workbook(
        [
            Cell(sheet="S", coordinate="A1", data_type="f", number_format="General", formula="=Missing!A1"),
            Cell(sheet="S", coordinate="A2", data_type="f", number_format="General", formula="=[Gone.xlsx]Data!A1"),
            Cell(sheet="S", coordinate="A3", data_type="f", number_format="General", formula="=S!B1"),
        ]
    )
    assert coordinates(checks.check_broken_links(workbook, Graph())) == {
        ("S", "A1"),
        ("S", "A2"),
    }
