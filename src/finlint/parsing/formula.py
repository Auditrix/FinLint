"""Work out which cells a formula reads from, in the reference format agreed in model.py."""

from openpyxl.formula import Tokenizer
from openpyxl.utils.cell import range_boundaries

# These functions take a cell but never read its value, they only ask where it
# sits. COLUMN(AA56) answers 27 whatever AA56 contains, so it is not a
# dependency. Treating it as one invented 120 false circular references in Fisy.
# Note: ROW() and COLUMN() with empty brackets mean "my own row" and "my own
# column". That is a dependency on position, not on a cell, so the map ignores it.
POSITION_FUNCTIONS = ("COLUMN", "ROW", "COLUMNS", "ROWS", "ADDRESS")


def make_ref(sheet, coord):
    """Build a reference, e.g. ("BFR", "B12") -> "BFR!B12". The only place refs are built."""
    return sheet + "!" + coord


def parse_ref(ref):
    """Split a reference on the last "!", e.g. "BFR!B12" -> ("BFR", "B12")."""
    if "!" not in ref:
        return "", ref
    sheet, _, coord = ref.rpartition("!")
    return sheet, coord


def _clean(piece, current_sheet):
    """Turn one raw range piece into the agreed format: sheet named, no quotes, no $."""
    if piece.startswith("["):  # external link, kept exactly as written
        return piece

    # Excel can repeat the sheet on both sides, e.g. "Commandes!$C9:Commandes!BJ9".
    left, separator, right = piece.partition(":")
    left_sheet, left_coord = parse_ref(left)
    right_sheet, right_coord = parse_ref(right)

    sheet = (left_sheet or right_sheet).replace("'", "") or current_sheet
    coord = left_coord.replace("$", "")
    if separator:
        coord = coord + ":" + right_coord.replace("$", "")
    return make_ref(sheet, coord)


def extract_refs(formula, current_sheet, defined_names):
    """Return the references a formula reads, deduplicated, in first seen order."""
    if formula is None:
        return []

    refs = []
    depth = 0             # how deep inside brackets we are
    position_depth = None # the depth a position function opened at, if we are in one

    for token in Tokenizer(formula).items:
        if token.subtype == "OPEN":  # a function bracket or a plain bracket
            depth += 1
            # Only the outermost position function matters, an inner one is
            # already being skipped.
            if (position_depth is None and token.type == "FUNC"
                    and token.value.rstrip("(").upper() in POSITION_FUNCTIONS):
                position_depth = depth
            continue

        if token.subtype == "CLOSE":
            if position_depth is not None and depth == position_depth:
                position_depth = None  # we have come back out of it
            depth -= 1
            continue

        if token.type != "OPERAND" or token.subtype != "RANGE":
            continue  # skip text, numbers and operators

        if position_depth is not None:
            continue  # inside COLUMN(...) and friends, the cell is not read

        if token.value in defined_names:
            # checked first: a short name like "DCF" would otherwise pass as a column
            ref = _clean(defined_names[token.value], current_sheet)
        else:
            try:
                range_boundaries(token.value.rpartition("!")[2])  # raises if not a real address
                ref = _clean(token.value, current_sheet)
            except ValueError:
                ref = token.value  # an undefined name, kept so nothing is lost

        if ref not in refs:
            refs.append(ref)

    return refs
