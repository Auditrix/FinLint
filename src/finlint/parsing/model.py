"""The shared shape of a workbook, agreed by Nara and Sowb on 16 September 2026.

Fields only. No methods, no logic. Every other file imports this one, so it
is frozen: change it only when both of us agree.
"""

from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, Field

# The seven Excel error strings, the same list openpyxl uses.
EXCEL_ERRORS = ("#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#N/A")

# Every kind of value a cell can hold. Shared by cached_value and calculated_value.
CellValue = bool | int | float | str | datetime | time | None


class Cell(BaseModel):
    """One non empty cell."""

    sheet: str                              # sheet this cell lives on
    coordinate: str                         # address, e.g. "B12"
    formula: str | None = None              # exact Excel text, keeps the leading "="
    data_type: str                          # openpyxl's code: "f" formula, "n", "s", ...
    cached_value: CellValue = None          # the answer Excel saved, or None
    calculated_value: CellValue = None      # our calculator's answer; only recalc writes it
    number_format: str                      # e.g. "General", "0.00%"
    array_range: str | None = None          # set only on the top left cell of an array formula
    refs: list[str] = Field(default_factory=list)  # what the formula reads; only formula.py writes it


class Sheet(BaseModel):
    """One worksheet."""

    name: str                                           # real name, real case
    state: Literal["visible", "hidden", "veryHidden"]   # openpyxl's exact spelling
    merged_ranges: list[str] = Field(default_factory=list)  # e.g. "C1:D1"
    cells: dict[str, Cell] = Field(default_factory=dict)    # keyed by coordinate


class Workbook(BaseModel):
    """One Excel file."""

    path: str                                                 # the file it came from
    sheets: dict[str, Sheet] = Field(default_factory=dict)    # keyed by sheet name, tab order
    defined_names: dict[str, str] = Field(default_factory=dict)  # name -> reference
