"""Check cell locations against the workbook we actually read."""

import re

from finlint.parsing.model import Workbook


CELL_ADDRESS = re.compile(r"(?<![A-Za-z0-9_])\$?[A-Za-z]{1,3}\$?\d+(?![A-Za-z0-9_])")
WHOLE_COORDINATE = re.compile(r"\$?([A-Za-z]{1,3})\$?([1-9]\d*)\Z")


def normalise_coordinate(coordinate: str) -> str | None:
    """Turn Excel's $C$15 spelling into the key used by our reader, C15."""
    if not isinstance(coordinate, str):
        return None
    match = WHOLE_COORDINATE.fullmatch(coordinate)
    if match is None:
        return None
    return f"{match.group(1).upper()}{match.group(2)}"


def verify_cell(workbook: Workbook, sheet: str, coordinate: str) -> bool:
    """True only when the sheet and nonempty cell are in the parsed workbook."""
    if not isinstance(sheet, str):
        return False
    worksheet = workbook.sheets.get(sheet)
    address = normalise_coordinate(coordinate)
    if worksheet is None or address is None:
        return False
    return address in worksheet.cells
