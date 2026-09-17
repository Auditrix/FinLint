from openpyxl import Workbook as OpenpyxlWorkbook

from finlint.parsing.reader import read_workbook
from finlint.parsing.recalc import recalculate_workbook, split_calculation_key


def make_calculation_workbook(path):
    workbook = OpenpyxlWorkbook()
    sheet = workbook.active
    sheet.title = "Profit and Loss"
    sheet["A1"] = 100
    sheet["A2"] = 30
    sheet["A3"] = "=A1-A2"
    workbook.save(path)


def test_split_calculation_key():
    key = "'[sample.xlsx]PROFIT AND LOSS'!A3"

    assert split_calculation_key(key) == ("PROFIT AND LOSS", "A3")


def test_recalculate_workbook(tmp_path):
    path = tmp_path / "sample.xlsx"
    make_calculation_workbook(path)
    original_file = path.read_bytes()

    workbook = read_workbook(path)
    result = recalculate_workbook(workbook)

    formula_cell = result.sheets["Profit and Loss"].cells["A3"]
    assert formula_cell.cached_value is None
    assert formula_cell.calculated_value == 70
    assert path.read_bytes() == original_file
