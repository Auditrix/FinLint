"""The fixed checks. Each one reads a workbook and its dependency map and
returns a list of Findings. No model is involved, every check has exactly one
correct answer, which is why these are plain code.

Every check has the same shape:  check_x(workbook, graph) -> list[Finding]
"""

import collections
import re

from openpyxl.utils.cell import column_index_from_string, coordinate_from_string

from finlint.graph.analyse import blast_radius, find_cycles
from finlint.graph.graph import Graph
from finlint.parsing.formula import extract_refs, make_ref, parse_ref
from finlint.parsing.model import EXCEL_ERRORS
from finlint.rules.model import Finding

# One cell reference, e.g. "B12", "$C$81", "AA7". Used to compare formula shapes.
# The guards on both sides stop it swallowing a function name that ends in a
# digit, such as LOG10, which would otherwise look exactly like a reference.
REFERENCE = re.compile(r"(?<![A-Za-z0-9_.])\$?[A-Za-z]{1,3}\$?\d+(?![A-Za-z0-9_.(])")


def _rows_by_number(sheet):
    """Group a sheet's cells into rows, each row sorted left to right."""
    rows = {}
    for cell in sheet.cells.values():
        letter, number = coordinate_from_string(cell.coordinate)
        rows.setdefault(number, []).append(cell)

    for cells in rows.values():
        cells.sort(key=lambda c: column_index_from_string(
            coordinate_from_string(c.coordinate)[0]))
    return rows


def check_error_cells(workbook, graph: Graph) -> list[Finding]:
    """A cell holding one of Excel's own error values, such as #REF!."""
    findings = []

    for sheet in workbook.sheets.values():
        for cell in sheet.cells.values():
            node = make_ref(cell.sheet, cell.coordinate)
            if cell.cached_value in EXCEL_ERRORS:
                findings.append(Finding(
                    rule_id="error_cells",
                    severity="high",
                    sheet=cell.sheet,
                    coordinate=cell.coordinate,
                    message=f"Cell contains an Excel error: {cell.cached_value}",
                    blast_radius=len(blast_radius(graph, node)),
                ))

    return findings


def check_circular(workbook, graph: Graph) -> list[Finding]:
    """Cells that depend on themselves through a loop."""
    findings = []

    for node in find_cycles(graph):
        sheet, coord = parse_ref(node)
        findings.append(Finding(
            rule_id="circular_reference",
            severity="critical",
            sheet=sheet,
            coordinate=coord,
            message=f"Cell {node} is part of a circular reference",
            blast_radius=len(blast_radius(graph, node)),
        ))

    return findings


def check_dead_inputs(workbook, graph: Graph) -> list[Finding]:
    """A typed number that no formula reads, so changing it changes nothing."""
    findings = []

    for sheet in workbook.sheets.values():
        # A sheet holding no formulas at all is a table of data, not a calculation,
        # so nothing on it reads anything and every cell would be reported.
        if not any(c.formula for c in sheet.cells.values()):
            continue

        for cell in sheet.cells.values():
            node = make_ref(cell.sheet, cell.coordinate)
            # Text is skipped, or every heading and label would be reported.
            if (cell.formula is None
                    and isinstance(cell.cached_value, (int, float))
                    and not graph.feeds_into.get(node)):
                findings.append(Finding(
                    rule_id="dead_input",
                    severity="low",
                    sheet=cell.sheet,
                    coordinate=cell.coordinate,
                    message=f"Cell {node} holds a typed value that no formula reads.",
                    blast_radius=len(blast_radius(graph, node)),
                ))

    return findings


def check_hardcoded_value(workbook, graph: Graph) -> list[Finding]:
    """A row that is mostly formulas, with one typed number sitting among them."""
    findings = []

    for sheet in workbook.sheets.values():
        for cells in _rows_by_number(sheet).values():
            formulas = [c for c in cells if c.formula]
            typed = [c for c in cells
                     if c.formula is None and isinstance(c.cached_value, (int, float))]

            if len(formulas) < 2 or len(typed) != 1:
                continue

            # It must sit between two formulas, otherwise an ordinary input
            # that merely shares a row with unrelated formulas gets reported.
            odd = typed[0]
            position = cells.index(odd)
            if position == 0 or position == len(cells) - 1:
                continue
            if not (cells[position - 1].formula and cells[position + 1].formula):
                continue

            node = make_ref(odd.sheet, odd.coordinate)
            findings.append(Finding(
                rule_id="hardcoded_value",
                severity="high",
                sheet=odd.sheet,
                coordinate=odd.coordinate,
                message=(f"Cell {node} holds a typed number where the rest of "
                         f"the row is calculated."),
                blast_radius=len(blast_radius(graph, node)),
            ))

    return findings


def check_broken_links(workbook, graph: Graph) -> list[Finding]:
    """A formula pointing at a sheet, a name or a workbook that is not there."""
    findings = []
    known_sheets = {name.casefold() for name in workbook.sheets}

    for sheet in workbook.sheets.values():
        for cell in sheet.cells.values():
            if cell.formula is None:
                continue

            for ref in extract_refs(cell.formula, cell.sheet, workbook.defined_names):
                sheet_name, coord = parse_ref(ref)

                if ref.startswith("["):
                    reason = f"reads from another workbook, which is not available: {ref}"
                elif not sheet_name:
                    # No sheet at all means extract_refs could not resolve a name,
                    # which is what Excel shows as #NAME?.
                    reason = f"uses the name {ref}, which is not defined anywhere"
                elif sheet_name.casefold() not in known_sheets:
                    # Excel treats sheet names as case insensitive, so Config and
                    # config are the same sheet and neither is a broken link.
                    reason = f"reads from a sheet that does not exist: {ref}"
                else:
                    continue

                node = make_ref(cell.sheet, cell.coordinate)
                findings.append(Finding(
                    rule_id="broken_link",
                    severity="medium",
                    sheet=cell.sheet,
                    coordinate=cell.coordinate,
                    message=f"Cell {node} {reason}",
                    blast_radius=len(blast_radius(graph, node)),
                ))

    return findings


def check_formula_drift(workbook, graph: Graph) -> list[Finding]:
    """One formula in a row whose shape differs from all its neighbours.

    Every cell reference is replaced by a marker before comparing, so
    "=B12-B13" and "=C12-C13" are both "=#-#", while "=D12" is just "=#".
    Stripping only the digits is not enough, because the column letters differ.
    """
    findings = []

    for sheet in workbook.sheets.values():
        for cells in _rows_by_number(sheet).values():
            formulas = [c for c in cells if c.formula]
            if len(formulas) < 3:
                continue  # with two formulas there is no majority to differ from

            shapes = [REFERENCE.sub("#", c.formula) for c in formulas]
            counted = collections.Counter(shapes)

            # Exactly one odd shape, and everything else agreeing on one shape.
            if len(counted) != 2:
                continue
            odd_shape, odd_count = counted.most_common()[-1]
            if odd_count != 1:
                continue

            odd = formulas[shapes.index(odd_shape)]
            node = make_ref(odd.sheet, odd.coordinate)
            findings.append(Finding(
                rule_id="formula_drift",
                severity="high",
                sheet=odd.sheet,
                coordinate=odd.coordinate,
                message=(f"Cell {node} holds {odd.formula}, which differs in shape "
                         f"from every other formula in its row."),
                blast_radius=len(blast_radius(graph, node)),
            ))

    return findings


ALL_CHECKS = (
    check_error_cells,
    check_circular,
    check_dead_inputs,
    check_hardcoded_value,
    check_broken_links,
    check_formula_drift,
)
