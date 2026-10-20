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


def test_dead_input_skips_year_headings_but_not_an_isolated_year_value():
    workbook = make_workbook(
        [
            Cell(sheet="S", coordinate="B2", data_type="n", number_format="General", cached_value=2021),
            Cell(sheet="S", coordinate="C2", data_type="n", number_format="General", cached_value=2022),
            Cell(sheet="S", coordinate="D2", data_type="n", number_format="General", cached_value=2023),
            Cell(sheet="S", coordinate="B5", data_type="n", number_format="General", cached_value=2022),
            Cell(sheet="S", coordinate="C5", data_type="n", number_format="General", cached_value=0.2),
            Cell(sheet="S", coordinate="D8", data_type="f", number_format="General", formula="=1+1"),
        ]
    )
    assert coordinates(checks.check_dead_inputs(workbook, Graph())) == {
        ("S", "B5"), ("S", "C5")
    }


def test_dead_input_skips_labelled_config_value_and_opening_zero():
    config = Sheet(name="Config", state="visible", cells={
        "B1": Cell(sheet="Config", coordinate="B1", data_type="s", number_format="General", cached_value="Salary rate"),
        "C1": Cell(sheet="Config", coordinate="C1", data_type="n", number_format="General", cached_value=0.22),
        "C2": Cell(sheet="Config", coordinate="C2", data_type="n", number_format="General", cached_value=42),
        "D3": Cell(sheet="Config", coordinate="D3", data_type="f", number_format="General", formula="=1+1"),
    })
    results = Sheet(name="Results", state="visible", cells={
        "B4": Cell(sheet="Results", coordinate="B4", data_type="s", number_format="General", cached_value="Opening balance"),
        "C4": Cell(sheet="Results", coordinate="C4", data_type="n", number_format="General", cached_value=0),
        "D4": Cell(sheet="Results", coordinate="D4", data_type="f", number_format="General", formula="=C4+1"),
    })
    workbook = Workbook(path="test.xlsx", sheets={"Config": config, "Results": results})
    assert coordinates(checks.check_dead_inputs(workbook, Graph())) == {("Config", "C2")}


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
