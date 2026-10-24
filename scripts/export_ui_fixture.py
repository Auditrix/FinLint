"""Export one real FinLint run as the JSON the frontend reads in sample mode.

Every value here is computed by the real backend on a real workbook: the
pipeline, the dependency graph, the version store and the diff. Nothing is
invented. The frontend falls back to these files when the API is not running,
and shows a banner saying so.

It is also a working reference for docs/api_contract.md. Each function below
builds the exact body one endpoint must return, so it is the quickest way to
see what the API has to produce.

Run from the repository root, with PostgreSQL up:

    python scripts/export_ui_fixture.py
    python scripts/export_ui_fixture.py --explain 4     # also ask Groq for 4 citations
"""

import argparse
import collections
import json
import shutil
from datetime import date, datetime, time, timezone
from pathlib import Path

from openpyxl.utils.cell import column_index_from_string, coordinate_from_string

from finlint.db.store import SCHEMA, load_history, save_run
from finlint.graph.analyse import blast_radius, dependents, precedents
from finlint.graph.build import build_graph
from finlint.lineage.diff import diff_runs, finding_key, first_seen
from finlint.parsing.formula import make_ref
from finlint.parsing.reader import read_workbook
from finlint.pipeline import check_file
from finlint.rag.store import connect
from finlint.rules.checks import REFERENCE

WORKBOOK = Path("data/seed_models/Financial_Models.xlsx")
OUT = Path("web/public/fixtures")

# A SUM over a whole column would otherwise send thousands of references.
REF_CAP = 50

# Cells either side of the target in the row view. A fifty column forecast row
# is unreadable in an inspector, and repeating whole rows for every cell made
# the payload balloon.
ROW_WINDOW = 8


def plain(value):
    """A cell value as something JSON can carry. Dates become ISO strings."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


def iso(moment) -> str:
    """An ISO timestamp in UTC. The contract requires UTC, and the database
    returns times in its own session timezone, which is not guaranteed to be."""
    return moment.astimezone(timezone.utc).isoformat()


def stats(workbook, graph) -> dict:
    return {
        "sheets": len(workbook.sheets),
        "cells": sum(len(s.cells) for s in workbook.sheets.values()),
        "formulas": sum(1 for s in workbook.sheets.values()
                        for c in s.cells.values() if c.formula),
        "links": sum(len(v) for v in graph.feeds.values()),
    }


def shape(formula):
    """One definition of a formula's shape, the same one formula_drift uses."""
    return REFERENCE.sub("#", formula) if formula else None


def inspect_cell(workbook, graph, sheet_name, coordinate) -> dict:
    """GET /api/files/{name}/cell?ref=... for one cell."""
    sheet = workbook.sheets[sheet_name]
    cell = sheet.cells[coordinate]
    ref = make_ref(sheet_name, coordinate)

    # Same row, left to right.
    _, row_number = coordinate_from_string(coordinate)
    siblings = []
    for other in sheet.cells.values():
        letter, number = coordinate_from_string(other.coordinate)
        if number == row_number:
            siblings.append((column_index_from_string(letter), other))
    siblings.sort(key=lambda pair: pair[0])

    full_row = [{
        "coordinate": other.coordinate,
        "formula": other.formula,
        "value": plain(other.cached_value),
        "shape": shape(other.formula),
        "is_target": other.coordinate == coordinate,
    } for _, other in siblings]

    # The majority is computed over the WHOLE row before the window is cut, so
    # the comparison is the same one formula_drift made.
    shapes = [r["shape"] for r in full_row if r["shape"]]
    counted = collections.Counter(shapes)
    majority, majority_count = counted.most_common(1)[0] if shapes else (None, 0)

    at = next(i for i, r in enumerate(full_row) if r["is_target"])
    row = full_row[max(0, at - ROW_WINDOW): at + ROW_WINDOW + 1]

    reads = sorted(precedents(graph, ref))
    readers = sorted(dependents(graph, ref))
    return {
        "ref": ref,
        "sheet": sheet_name,
        "coordinate": coordinate,
        "formula": cell.formula,
        "value": plain(cell.cached_value),
        "number_format": cell.number_format,
        "precedents": reads[:REF_CAP],
        "precedents_total": len(reads),
        "dependents": readers[:REF_CAP],
        "dependents_total": len(readers),
        "blast_radius": len(blast_radius(graph, ref)),
        "row": row,
        "row_total": len(full_row),
        "majority_shape": majority,
        # Both counted over the whole row, like majority_shape. The window above
        # shows at most seventeen cells, so counting what is shown under-reports.
        "majority_count": majority_count,
        "formula_count": len(shapes),
    }


def run_body(conn, name, workbook, graph) -> dict:
    """GET /api/files/{name}/run for the latest version."""
    history = load_history(conn, name)
    latest, previous = history[-1], (history[-2] if len(history) > 1 else None)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT r.id, r.created_at, r.sha256, r.score FROM runs r "
            "JOIN files f ON f.id = r.file_id WHERE f.name = %s "
            "ORDER BY r.version DESC, r.id DESC LIMIT 2", (name,))
        rows = cur.fetchall()
    run_id, created_at, sha256, score = rows[0]
    previous_sha = rows[1][2] if len(rows) > 1 else None

    difference = diff_runs(previous.findings if previous else [], latest.findings)
    new_keys = {finding_key(f) for f in difference.new}

    with conn.cursor() as cur:
        cur.execute(
            "SELECT a.rule_id, a.sheet, a.coordinate FROM approvals a "
            "JOIN files f ON f.id = a.file_id WHERE f.name = %s", (name,))
        approved = {tuple(r) for r in cur.fetchall()}

    findings = []
    for f in latest.findings:
        body = f.model_dump()
        body["status"] = "new" if finding_key(f) in new_keys else "still_there"
        body["first_seen"] = first_seen(f, history)
        body["approved"] = finding_key(f) in approved
        findings.append(body)

    return {
        "file": name,
        "run_id": run_id,
        "version": latest.version,
        "previous_version": previous.version if previous else None,
        "created_at": iso(created_at),
        "sha256": sha256,
        "unchanged_since_previous": previous_sha is not None and previous_sha == sha256,
        "score": score,
        "stats": stats(workbook, graph),
        "findings": findings,
        "resolved": [f.model_dump() for f in difference.resolved],
    }


def history_body(conn, name) -> list:
    """GET /api/files/{name}/history."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT r.version, r.id, r.created_at, r.score, r.sha256 FROM runs r "
            "JOIN files f ON f.id = r.file_id WHERE f.name = %s "
            "ORDER BY r.version, r.id", (name,))
        meta = cur.fetchall()

    records = {r.version: r for r in load_history(conn, name)}
    out = []
    for version, run_id, created_at, score, sha256 in meta:
        found = records[version].findings if version in records else []
        counts = collections.Counter(f.severity for f in found)
        out.append({
            "version": version,
            "run_id": run_id,
            "created_at": iso(created_at),
            "score": score,
            "sha256": sha256,
            "counts": {s: counts.get(s, 0) for s in ("critical", "high", "medium", "low")},
            "total": len(found),
        })
    return out


def files_body(conn, name) -> list:
    """GET /api/files, restricted to the one workbook this sample covers.

    The live endpoint lists every file. The sample must not: run.json, history
    and cells cover only one workbook, so listing others let the dropdown show
    one file's findings under another file's name.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ON (f.name) f.name, r.version, r.score, r.created_at, r.id "
            "FROM files f JOIN runs r ON r.file_id = f.id WHERE f.name = %s "
            "ORDER BY f.name, r.version DESC, r.id DESC", (name,))
        rows = cur.fetchall()
        out = []
        for file_name, version, score, created_at, run_id in rows:
            cur.execute("SELECT count(*) FROM findings WHERE run_id = %s", (run_id,))
            out.append((created_at, {
                "name": file_name,
                "latest_version": version,
                "latest_score": score,
                "latest_at": iso(created_at),
                "finding_count": cur.fetchone()[0],
            }))
    # Sorted on the datetime, not on its string, which misorders mixed offsets.
    return [body for _, body in sorted(out, key=lambda pair: pair[0], reverse=True)]


def approvals_body(conn, name) -> list:
    """GET /api/files/{name}/approvals: every decision row, newest first."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT a.rule_id, a.sheet, a.coordinate, a.reason, a.decided_by, a.decided_at "
            "FROM approvals a JOIN files f ON f.id = a.file_id WHERE f.name = %s "
            "ORDER BY a.decided_at DESC, a.id DESC", (name,))
        return [{
            "rule_id": rule_id, "sheet": sheet, "coordinate": coordinate,
            "reason": reason, "decided_by": decided_by, "decided_at": iso(decided_at),
        } for rule_id, sheet, coordinate, reason, decided_by, decided_at in cur.fetchall()]


def explanations(conn, findings, how_many) -> dict:
    """POST /api/explain for a few findings, one per rule, through Groq."""
    from finlint.agents.groq_provider import groq_completion
    from finlint.agents.standards import explain_with_retriever

    complete = groq_completion("qwen/qwen3.8-27b")
    picked, seen_rules = [], set()
    for f in findings:
        if f.rule_id not in seen_rules:
            picked.append(f)
            seen_rules.add(f.rule_id)
        if len(picked) == how_many:
            break

    out = {}
    for f in picked:
        key = f"{f.rule_id}|{make_ref(f.sheet, f.coordinate)}"
        try:
            result = explain_with_retriever(conn, f, complete, limit=5)
            out[key] = result.model_dump()
            print(f"  explained {key}: supported={result.supported}")
        except Exception as error:  # record honestly rather than invent one
            print(f"  could not explain {key}: {error}")
    return out


def write(name, body):
    path = OUT / name
    path.write_text(json.dumps(body, indent=None, default=str), encoding="utf-8")
    print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--explain", type=int, default=0,
                        help="ask the Standards agent for this many findings")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    conn = connect()
    with conn.cursor() as cur:
        for statement in SCHEMA:
            cur.execute(statement)
    conn.commit()

    name = WORKBOOK.name
    result = check_file(str(WORKBOOK))

    # This run is always stored, so the latest version IS what the current code
    # found. Reusing older stored runs made run.json describe old rules while
    # stats, cells and explanations described new ones. A second copy is added
    # only on a first export, so history has two versions to compare.
    save_run(conn, result)
    if len(load_history(conn, name)) < 2:
        save_run(conn, result)

    workbook = read_workbook(str(WORKBOOK))
    graph = build_graph(workbook)

    run = run_body(conn, name, workbook, graph)
    write("run.json", run)
    write("history.json", history_body(conn, name))
    write("files.json", files_body(conn, name))

    cells = {}
    for f in run["findings"]:
        ref = make_ref(f["sheet"], f["coordinate"])
        if ref not in cells and f["sheet"] in workbook.sheets \
                and f["coordinate"] in workbook.sheets[f["sheet"]].cells:
            cells[ref] = inspect_cell(workbook, graph, f["sheet"], f["coordinate"])
    write("cells.json", cells)

    write("approvals.json", approvals_body(conn, name))

    # Only rewritten when asked. Each explanation costs real Groq calls, and a
    # plain re-export used to overwrite the saved ones with an empty file.
    if args.explain:
        explained = explanations(conn, result.findings, args.explain)
        write("explanations.json", explained)
    else:
        saved = OUT / "explanations.json"
        explained = json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else {}
        print(f"kept {saved} ({len(explained)} saved explanations)")

    shutil.copy("docs/evaluation.json", OUT / "evaluation.json")
    print(f"copied docs/evaluation.json to {OUT / 'evaluation.json'}")

    write("health.json", {"ok": True, "database": True,
                          "llm": bool(explained), "version": "0.1.0"})


if __name__ == "__main__":
    main()
