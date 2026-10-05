"""Create reproducible formula faults and label the cell that was changed."""

import argparse
import json
import random
import re
import shutil
from pathlib import Path

from openpyxl import load_workbook

MUTATIONS = ("swap_operator", "shift_reference", "blank_formula")
CELL_REFERENCE = re.compile(r"(?<![A-Z0-9_.])(\$?[A-Z]{1,3})(\$?)([1-9][0-9]*)(?!\s*\()")


def swap_operator(formula: str, rng: random.Random) -> str | None:
    """Change one arithmetic operator without changing the rest of the formula."""
    replacements = {
        "+": "-",
        "-": "+",
        "*": "/",
        "/": "*",
        "^": "*",
    }
    positions = []
    inside_text = False

    for index, character in enumerate(formula):
        if character == '"':
            inside_text = not inside_text
            continue
        if inside_text or index == 0 or character not in replacements:
            continue

        previous = formula[index - 1]
        if character in "+-" and previous in "=(,+-*/^":
            continue
        positions.append(index)

    if not positions:
        return None

    index = rng.choice(positions)
    return formula[:index] + replacements[formula[index]] + formula[index + 1 :]


def shift_reference(formula: str, rng: random.Random) -> str | None:
    """Move one cell reference up or down by one row."""
    matches = list(CELL_REFERENCE.finditer(formula))
    if not matches:
        return None

    match = rng.choice(matches)
    old_row = int(match.group(3))
    choices = [old_row + 1]
    if old_row > 1:
        choices.append(old_row - 1)
    new_row = rng.choice(choices)

    changed_reference = match.group(1) + match.group(2) + str(new_row)
    return formula[: match.start()] + changed_reference + formula[match.end() :]


def mutate_formula(formula: str, mutation: str, rng: random.Random):
    """Return the changed formula, or None when the formula is blanked."""
    if mutation == "swap_operator":
        return swap_operator(formula, rng)
    if mutation == "shift_reference":
        return shift_reference(formula, rng)
    if mutation == "blank_formula":
        return None
    raise ValueError(f"Unknown mutation: {mutation}")


def formula_cells(path: str | Path) -> list[tuple[str, str, str]]:
    """Return ordinary formula cells that are safe to change one at a time."""
    path = Path(path)
    workbook = load_workbook(path, data_only=False, keep_vba=path.suffix.lower() == ".xlsm")
    cells = []

    try:
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.data_type == "f" and isinstance(cell.value, str):
                        cells.append((sheet.title, cell.coordinate, cell.value))
    finally:
        workbook.close()

    return cells


def write_mutated_copy(
    source_path: str | Path,
    destination_path: str | Path,
    sheet: str,
    coordinate: str,
    new_value,
) -> Path:
    """Copy a workbook and change one cell, leaving the source untouched."""
    source_path = Path(source_path)
    destination_path = Path(destination_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)

    workbook = load_workbook(
        destination_path,
        data_only=False,
        keep_vba=destination_path.suffix.lower() == ".xlsm",
    )
    try:
        workbook[sheet][coordinate] = new_value
        workbook.save(destination_path)
    finally:
        workbook.close()

    return destination_path


def load_faults(path: str | Path) -> list[dict]:
    """Read previously saved JSONL fault records."""
    path = Path(path)
    if not path.exists():
        return []

    records = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                records.append(json.loads(line))
    return records


def save_fault(path: str | Path, record: dict) -> None:
    """Append one completed fault so a long run can be resumed later."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=True) + "\n")


def generate_faults(
    source_path: str | Path,
    output_path: str | Path,
    target_faults: int = 1000,
    seed: int = 42,
    max_attempts: int = 5000,
) -> list[dict]:
    """Generate faults and use each injected cell as its own answer label."""
    source_path = Path(source_path).resolve()
    output_path = Path(output_path)
    rng = random.Random(seed)
    candidates = formula_cells(source_path)
    if not candidates:
        raise ValueError(f"No ordinary formula cells found in {source_path}")

    records = load_faults(output_path)
    if any("labelled_cell" not in record for record in records):
        raise ValueError("Existing output uses the old downstream-cell label format")

    used_cells = {(record["sheet"], record["coordinate"]) for record in records}

    attempts = 0
    while len(records) < target_faults and attempts < max_attempts:
        attempts += 1
        sheet, coordinate, original_formula = rng.choice(candidates)
        if (sheet, coordinate) in used_cells:
            continue

        mutation = rng.choice(MUTATIONS)
        mutated_formula = mutate_formula(original_formula, mutation, rng)

        if mutation != "blank_formula" and mutated_formula is None:
            continue

        record = {
            "fault_id": len(records) + 1,
            "source_path": str(source_path),
            "sheet": sheet,
            "coordinate": coordinate,
            "mutation": mutation,
            "original_formula": original_formula,
            "mutated_formula": mutated_formula,
            "labelled_cell": f"{sheet}!{coordinate}",
        }
        save_fault(output_path, record)
        records.append(record)
        used_cells.add((sheet, coordinate))

        if len(records) % 100 == 0 or len(records) >= target_faults:
            print(f"saved {len(records)} labelled faults")

    if len(records) < target_faults:
        raise RuntimeError(f"Stopped after {attempts} attempts with only {len(records)} faults")

    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Plant faults in a workbook")
    parser.add_argument("source", help="clean .xlsx or .xlsm workbook")
    parser.add_argument("output", help="JSONL file for the fault records")
    parser.add_argument("--target", type=int, default=1000, help="fault cells to create")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-attempts", type=int, default=5000)
    args = parser.parse_args()

    generate_faults(args.source, args.output, args.target, args.seed, args.max_attempts)


if __name__ == "__main__":
    main()
