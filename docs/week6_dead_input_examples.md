# Dead-input review examples

These 20 cells are from the two seed workbook families, not from the ExcelInt
answer key. They are examples for discussing the rule, not proof that every
remaining finding is wrong.

| Workbook | Sheet and cell | Stored value | What the cell appears to be | New filter |
| --- | --- | ---: | --- | --- |
| FISY-ESSENTIEL | Config!C71 | 0.22 | Labeled salary-charge setting | Skip labeled config value |
| FISY-ESSENTIEL | Comptes de resultats!C33 | 0 | Opening deficit amount before formula periods | Skip opening zero |
| FISY-INNOVATION | CONFIG!C90 | 0.22 | Labeled salary-charge setting | Skip labeled config value |
| FISY-INNOVATION | Comptes de resultats!C34 | 0 | Opening deficit amount before formula periods | Skip opening zero |
| Financial_Models | IS Hist Forecast!D3 | 2019 | Year heading beside 2020 | Skip consecutive-year heading |
| Financial_Models | IS Hist Forecast!E3 | 2020 | Year heading between 2019 and 2021 | Skip consecutive-year heading |
| Financial_Models | BAL Hist Forecast!H3 | 2022 | Year heading beside 2023 | Skip consecutive-year heading |
| Financial_Models | BAL Hist Forecast!I3 | 2023 | Year heading between 2022 and 2024 | Skip consecutive-year heading |
| Financial_Models | CF Statement Forecast!D3 | 2022 | Year heading beside 2023 | Skip consecutive-year heading |
| Financial_Models | CF Statement Forecast!E3 | 2023 | Year heading between 2022 and 2024 | Skip consecutive-year heading |
| Financial_Models | Supporting Schedules!D2 | 2021 | Year heading beside 2022 | Skip consecutive-year heading |
| Financial_Models | Supporting Schedules!E2 | 2022 | Year heading between 2021 and 2023 | Skip consecutive-year heading |
| Financial_Models | Beta computation!A2 | 18163 | PERMNO identifier in a raw data table | Still flagged |
| Financial_Models | Beta computation!F2 | 21446 | PERMCO identifier in a raw data table | Still flagged |
| Financial_Models | Beta computation!I2 | 71.84 | Historical market price in a raw data table | Still flagged |
| Financial_Models | WACC and Growth!P8 | 0.025 | What-if table column input | Still flagged |
| Financial_Models | WACC and Growth!Q8 | 0.03 | What-if table column input | Still flagged |
| Financial_Models | Balance Sheet!B9 | 5017 | Historical inventory value | Still flagged |
| Financial_Models | WACC_growth_HARDCODE!B1 | 0.04 | Labeled WACC assumption | Still flagged |
| Financial_Models | MV Debt and Weighted YTM (Rd)!D39 | 2022 | Bond maturity year in a data row, not a heading | Still flagged |

The Fisy sheet names contain accented characters in the workbooks; the table
uses plain ASCII spellings only for readability. Use the workbook's exact sheet
name when locating a cell.

On the 70 untouched ExcelInt workbooks, the original report had 92 true
positives and 17,662 false positives. After these filters it has 92 true
positives and 17,251 false positives. Recall stays 13.14%. The new report is
saved locally in `data/generated/tier_two_after_dead_input_filters.json`.

The large Beta computation data block is still flagged because the rule only
knows whether formulas refer to a number. The WACC what-if table has the same
problem: its inputs are used by an Excel data-table feature, not by ordinary
formula references in our graph. These need separate review before adding
another filter.
