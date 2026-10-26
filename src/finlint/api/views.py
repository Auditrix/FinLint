"""Build the JSON bodies the API returns, exactly as docs/api_contract.md says.

These functions are shared by two callers on purpose: the live API in
api/main.py, and scripts/export_ui_fixture.py, which writes the saved sample
the frontend falls back to. Because both use this one module, the sample and
the live API can never disagree about a field.

Every function takes an open connection and plain values, and returns plain
dicts and lists that FastAPI can send as they are. None of them opens,
commits or closes the connection: that belongs to the caller.
"""

import collections
from datetime import date, datetime, time, timezone

from openpyxl.utils.cell import column_index_from_string, coordinate_from_string

from finlint.db.store import load_history
from finlint.graph.analyse import blast_radius, dependents, precedents
from finlint.lineage.diff import diff_runs, finding_key, first_seen
from finlint.parsing.formula import make_ref
from finlint.rules.checks import REFERENCE

# A SUM over a whole column would otherwise send thousands of references.
REF_CAP = 50

# Cells either side of the target in the row view. A fifty column forecast row
# is unreadable in an inspector, and repeating whole rows for every cell made
# the payload balloon.
ROW_WINDOW = 8

SEVERITIES = ("critical", "high", "medium", "low")


class NotFound(LookupError):
    """The workbook, sheet or cell asked for does not exist.

    Raised instead of letting an IndexError or KeyError escape, so the API can
    answer 404 with a readable message rather than 500 with a stack trace.
    The message is written for the person using the page.
    """


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
    """Size of the workbook and its dependency map, for the metric cards."""
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
    sheet = workbook.sheets.get(sheet_name)
    if sheet is None:
        raise NotFound(f"There is no sheet called {sheet_name} in this workbook.")
    cell = sheet.cells.get(coordinate)
    if cell is None:
        raise NotFound(f"{make_ref(sheet_name, coordinate)} is empty or does not exist.")
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
    """GET /api/files/{name}/run for the latest version.

    workbook and graph are the parsed latest version of this file, used for
    the size figures. Raises NotFound when the file has never been checked.
    """
    history = load_history(conn, name)
    if not history:
        raise NotFound(f"{name} has not been checked yet.")
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
    """GET /api/files/{name}/history, every version oldest first."""
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
            "counts": {s: counts.get(s, 0) for s in SEVERITIES},
            "total": len(found),
        })
    return out


def files_body(conn, name=None) -> list:
    """GET /api/files: every checked workbook, newest check first.

    Pass name to restrict it to one workbook. The saved sample does, because
    its run, history and cells cover only one file, and listing others let the
    dropdown show one file's findings under another file's name. The live API
    passes nothing and lists them all.
    """
    where, params = ("WHERE f.name = %s ", (name,)) if name else ("", ())
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ON (f.name) f.name, r.version, r.score, r.created_at, r.id "
            "FROM files f JOIN runs r ON r.file_id = f.id " + where +
            "ORDER BY f.name, r.version DESC, r.id DESC", params)
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
    """GET /api/files/{name}/approvals: every decision row, newest first.

    Every row, including two decisions on one cell. db.store.load_approvals
    returns only the set of accepted keys, which is right for greying findings
    out but loses the audit trail this endpoint exists to show.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT a.rule_id, a.sheet, a.coordinate, a.reason, a.decided_by, a.decided_at "
            "FROM approvals a JOIN files f ON f.id = a.file_id WHERE f.name = %s "
            "ORDER BY a.decided_at DESC, a.id DESC", (name,))
        return [{
            "rule_id": rule_id, "sheet": sheet, "coordinate": coordinate,
            "reason": reason, "decided_by": decided_by, "decided_at": iso(decided_at),
        } for rule_id, sheet, coordinate, reason, decided_by, decided_at in cur.fetchall()]
