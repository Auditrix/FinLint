"""Calculate workbook formulas without changing the original Excel file."""

import shutil
from datetime import datetime, time
from pathlib import Path
from tempfile import TemporaryDirectory

import formulas

from finlint.parsing.model import Workbook


def split_calculation_key(key):
    """Get the sheet and coordinate from a key returned by formulas."""
    # Example key: '[sample.xlsx]PROFIT AND LOSS'!A3
    closing_bracket = key.find("]")
    cell_separator = key.rfind("'!")

    if closing_bracket == -1 or cell_separator == -1:
        return None, None

    sheet_name = key[closing_bracket + 1 : cell_separator]
    coordinate = key[cell_separator + 2 :].upper()

    # Range results are also returned, but here I only need single cells.
    if not coordinate.isalnum() or not any(char.isdigit() for char in coordinate):
        return None, None

    sheet_name = sheet_name.replace("''", "'")
    return sheet_name, coordinate


def find_real_sheet_name(workbook, calculated_name):
    """Match an upper-case calculator name with the real Excel sheet name."""
    for real_name in workbook.sheets:
        if real_name.casefold() == calculated_name.casefold():
            return real_name

    return None


def get_calculated_value(result):
    """Take one normal Python value out of a formulas result."""
    value = getattr(result, "value", result)

    # A single Excel cell is normally returned inside a 1 by 1 array.
    try:
        value = value[0, 0]
    except (IndexError, KeyError, TypeError):
        pass

    # NumPy numbers have an item method that gives a normal Python number.
    if hasattr(value, "item"):
        value = value.item()

    if value is None or isinstance(value, (bool, int, float, str, datetime, time)):
        return value

    # Excel errors from formulas become readable strings such as #NAME?.
    return str(value)


def recalculate_workbook(workbook: Workbook) -> Workbook:
    """Calculate formulas and fill calculated_value in the shared workbook."""
    source_path = Path(workbook.path)

    if not source_path.exists():
        raise FileNotFoundError(f"Workbook not found: {source_path}")

    # I use a temporary copy so the original workbook is never changed.
    with TemporaryDirectory() as temporary_folder:
        copied_path = Path(temporary_folder) / source_path.name
        shutil.copy2(source_path, copied_path)

        excel_model = formulas.ExcelModel().loads(str(copied_path)).finish(circular=True)
        calculation = excel_model.calculate()

    for key, result in calculation.items():
        calculated_sheet, coordinate = split_calculation_key(str(key))
        if calculated_sheet is None:
            continue

        real_sheet = find_real_sheet_name(workbook, calculated_sheet)
        if real_sheet is None:
            continue

        cell = workbook.sheets[real_sheet].cells.get(coordinate)
        if cell is None or cell.formula is None:
            continue

        cell.calculated_value = get_calculated_value(result)

    return workbook
