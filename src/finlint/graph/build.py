"""Turn a Workbook into a dependency map, so we can ask what feeds what.

This is the only file that writes to a Graph. analyse.py only reads one.
"""

from openpyxl.utils.cell import get_column_letter, range_boundaries

from finlint.graph.graph import MAX_RANGE_CELLS, Graph
from finlint.parsing.formula import extract_refs, make_ref, parse_ref


def expand_range(ref):
    """Split a reference into single cell nodes, e.g. "S!B1:B3" -> three nodes.

    Anything we cannot or should not split is returned unchanged, as one node.
    """
    sheet, coord = parse_ref(ref)

    if sheet.startswith("["):  # a link to another workbook
        return [ref]

    if ":" not in coord:  # already a single cell, or a bare defined name
        return [ref]

    min_col, min_row, max_col, max_row = range_boundaries(coord)

    # A whole column or row leaves two of these empty, and it is far too big to split.
    if min_col is None or min_row is None or max_col is None or max_row is None:
        return [ref]

    # A very large range would swamp the map, so it stays as one node.
    if (max_row - min_row + 1) * (max_col - min_col + 1) > MAX_RANGE_CELLS:
        return [ref]

    cells = []
    for row in range(min_row, max_row + 1):
        for col in range(min_col, max_col + 1):
            col_letter = get_column_letter(col)
            cells.append(make_ref(sheet, f"{col_letter}{row}"))
    return cells


def build_graph(workbook):
    """Read every formula in the workbook and return the finished dependency map."""
    graph = Graph()

    for sheet in workbook.sheets.values():
        for cell in sheet.cells.values():
            # Typed numbers and text read nothing, so they start no links.
            if not cell.formula:
                continue

            node = make_ref(cell.sheet, cell.coordinate)

            # The reader leaves refs empty, so the references are worked out here.
            for ref in extract_refs(cell.formula, cell.sheet, workbook.defined_names):
                for target in expand_range(ref):
                    # Every link is stored twice, once in each direction,
                    # so both questions are a single lookup later.
                    graph.feeds.setdefault(node, set()).add(target)
                    graph.feeds_into.setdefault(target, set()).add(node)

    return graph
