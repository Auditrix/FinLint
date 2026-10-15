"""The cell guardrail checks the parsed workbook, not a model's guess."""

from finlint.guardrails.cells import verify_cell
from finlint.parsing.model import Cell, Sheet, Workbook


def sample_workbook():
    cell = Cell(sheet="P&L", coordinate="C15", data_type="n", cached_value=10,
                number_format="General")
    sheet = Sheet(name="P&L", state="visible", cells={"C15": cell})
    return Workbook(path="sample.xlsx", sheets={"P&L": sheet})


def test_real_cell_passes_with_normal_excel_spellings():
    workbook = sample_workbook()
    assert verify_cell(workbook, "P&L", "C15") is True
    assert verify_cell(workbook, "P&L", "$c$15") is True


def test_missing_or_malformed_cell_fails():
    workbook = sample_workbook()
    assert verify_cell(workbook, "P&L", "Z999") is False
    assert verify_cell(workbook, "Other", "C15") is False
    assert verify_cell(workbook, "P&L", "C0") is False
    assert verify_cell(workbook, "P&L", "C15:D15") is False
