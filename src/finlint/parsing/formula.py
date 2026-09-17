"""Work out which cells a formula reads from, in the reference format agreed in model.py."""

from openpyxl.formula import Tokenizer
from openpyxl.utils.cell import range_boundaries


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
    sheet, coord = parse_ref(piece)
    sheet = sheet.replace("'", "") or current_sheet
    coord = coord.replace("$", "")
    return make_ref(sheet, coord)


def extract_refs(formula, current_sheet, defined_names):
    """Return the references a formula reads, deduplicated, in first seen order."""
    if formula is None:
        return []

    refs = []
    for token in Tokenizer(formula).items:
        if token.type != "OPERAND" or token.subtype != "RANGE":
            continue  # skip text, numbers, functions and operators

        try:
            range_boundaries(token.value.rpartition("!")[2])  # raises if not a real address
            ref = _clean(token.value, current_sheet)
        except ValueError:
            # a defined name: use what it points to, or keep the bare name
            ref = defined_names.get(token.value, token.value)

        if ref not in refs:
            refs.append(ref)

    return refs
