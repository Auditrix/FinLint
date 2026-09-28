# Test fixtures

Five small workbooks, each carrying one deliberate problem. They are committed
so tests never need a download. Rebuild them at any time with:

    python tests/fixtures/make_fixtures.py

Verified against `reader.py`, `build.py` and `analyse.py` on 28 September 2026.
The counts below are what those modules actually return today, so a test can
assert on them directly.

| File | Contains | What a rule must find | Verified now |
|---|---|---|---|
| `circular.xlsx` | `Loop!A1` and `A2` read each other, and `C1 -> C2 -> C3 -> C1`. `E1` and `E2` are clean | 5 cells in a loop, and `E1`, `E2` reported clean | `find_cycles` returns exactly `Loop!A1, A2, C1, C2, C3` |
| `hardcode.xlsx` | `P&L!C15` holds the typed number 72 where `B15` and `D15` hold `=B12-B13` | 1 hardcoded value at `P&L!C15` | 9 cells, 2 formulas, so `C15` is the odd one out |
| `brokenlink.xlsx` | `A1` points at a sheet that does not exist, `A2` at a workbook that does not exist, `A3` holds `#REF!` | 2 broken links and 1 error cell | error cell found at `A3` |
| `arrayformula.xlsx` | One array formula at `Calc!D1` covering `D1:D3` | the array must be read, not skipped | 1 array, `array_range` is `D1:D3` |
| `merged.xlsx` | `A1:D1` merged with a title, `A5:B6` merged and empty | both merges must survive the reader | `merged_ranges` is `A1:D1, A5:B6` |

## Why these five

Each one breaks a different part of the pipeline if it is handled wrongly.
The merged and array cases are reader problems. The circular case is a graph
problem. The hardcode and broken link cases are rule engine problems, and they
are the first two checks worth writing in Week 4.
