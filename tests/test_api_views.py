"""Tests for api/views.py, the JSON the API and the saved sample both return.

The cell inspection needs only a workbook, so those tests use the committed
fixtures and run in CI. The ones that need run history are skipped when no
PostgreSQL is reachable.
"""

import pytest

from finlint.api.views import (
    REF_CAP,
    ROW_WINDOW,
    NotFound,
    files_body,
    inspect_cell,
    run_body,
    shape,
    stats,
)
from finlint.graph.build import build_graph
from finlint.parsing.reader import read_workbook
from finlint.rules.checks import REFERENCE

# Every key the frontend reads from GET /api/files/{name}/cell.
CELL_KEYS = {
    "ref", "sheet", "coordinate", "formula", "value", "number_format",
    "precedents", "precedents_total", "dependents", "dependents_total",
    "blast_radius", "row", "row_total", "majority_shape",
    "majority_count", "formula_count",
}


def load(name):
    workbook = read_workbook(f"tests/fixtures/{name}")
    return workbook, build_graph(workbook)


def first_formula_cell(workbook):
    for sheet in workbook.sheets.values():
        for cell in sheet.cells.values():
            if cell.formula:
                return sheet.name, cell.coordinate
    raise AssertionError("fixture has no formula")


def _database_available():
    try:
        from finlint.rag.store import connect
        connect().close()
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(not _database_available(), reason="no reachable PostgreSQL")


# --- shape: one definition shared with formula_drift ------------------------

def test_shape_uses_the_same_rule_as_formula_drift():
    """If these ever diverge, the inspector would explain a drift the rule
    never saw, or miss one it did."""
    assert shape("=B12-B13") == REFERENCE.sub("#", "=B12-B13") == "=#-#"


def test_a_typed_value_has_no_shape():
    assert shape(None) is None


# --- inspect_cell: GET /api/files/{name}/cell -------------------------------

def test_every_contract_key_is_present():
    """The frontend reads each of these. A missing one fails silently there."""
    workbook, graph = load("circular.xlsx")
    sheet, coordinate = first_formula_cell(workbook)

    assert set(inspect_cell(workbook, graph, sheet, coordinate)) == CELL_KEYS


def test_the_target_is_marked_once_in_its_row():
    workbook, graph = load("drift.xlsx")
    sheet, coordinate = first_formula_cell(workbook)

    row = inspect_cell(workbook, graph, sheet, coordinate)["row"]

    assert [r["coordinate"] for r in row if r["is_target"]] == [coordinate]


def test_the_row_window_is_capped_but_the_counts_are_not():
    """At most ROW_WINDOW cells either side are sent, while row_total,
    majority_count and formula_count describe the whole row. Counting only
    the cells shown under-reported on any wide row."""
    workbook, graph = load("drift.xlsx")
    sheet, coordinate = first_formula_cell(workbook)

    cell = inspect_cell(workbook, graph, sheet, coordinate)

    assert len(cell["row"]) <= ROW_WINDOW * 2 + 1
    assert cell["row_total"] >= len(cell["row"])
    assert cell["formula_count"] >= cell["majority_count"]


def test_reference_lists_are_capped_with_true_totals():
    workbook, graph = load("circular.xlsx")
    sheet, coordinate = first_formula_cell(workbook)

    cell = inspect_cell(workbook, graph, sheet, coordinate)

    assert len(cell["precedents"]) <= REF_CAP
    assert cell["precedents_total"] >= len(cell["precedents"])
    assert len(cell["dependents"]) <= REF_CAP
    assert cell["dependents_total"] >= len(cell["dependents"])


def test_an_unknown_sheet_is_not_found():
    """A readable 404, not a KeyError surfacing as a server error."""
    workbook, graph = load("circular.xlsx")

    with pytest.raises(NotFound, match="no sheet called"):
        inspect_cell(workbook, graph, "No Such Sheet", "A1")


def test_an_empty_cell_is_not_found():
    workbook, graph = load("circular.xlsx")
    sheet, _ = first_formula_cell(workbook)

    with pytest.raises(NotFound, match="empty or does not exist"):
        inspect_cell(workbook, graph, sheet, "ZZ9999")


# --- stats ------------------------------------------------------------------

def test_stats_count_formulas_and_links():
    workbook, graph = load("circular.xlsx")

    figures = stats(workbook, graph)

    assert figures["formulas"] > 0
    assert figures["links"] == sum(len(v) for v in graph.feeds.values())


# --- needing run history ----------------------------------------------------

@needs_db
def test_a_file_never_checked_is_not_found():
    """run_body used to raise IndexError here, which the API would send as 500."""
    from finlint.rag.store import connect

    workbook, graph = load("circular.xlsx")
    conn = connect()
    try:
        with pytest.raises(NotFound, match="has not been checked"):
            run_body(conn, "zz_never_checked.xlsx", workbook, graph)
    finally:
        conn.close()


@needs_db
def test_files_can_be_restricted_to_one_name():
    """The saved sample lists one workbook; the live API lists them all."""
    from finlint.rag.store import connect

    conn = connect()
    try:
        assert files_body(conn, "zz_never_checked.xlsx") == []
        assert isinstance(files_body(conn), list)
    finally:
        conn.close()
