"""Export one real FinLint run as the JSON the frontend reads in sample mode.

Every value here is computed by the real backend on a real workbook: the
pipeline, the dependency graph, the version store and the diff. Nothing is
invented. The frontend falls back to these files when the API is not running,
and shows a banner saying so.

The JSON itself is built by finlint.api.views, the same module the live API
uses, so the saved sample and the API cannot drift apart. This script only
decides which workbook to export and where to write it.

Run from the repository root, with PostgreSQL up:

    python scripts/export_ui_fixture.py
    python scripts/export_ui_fixture.py --explain 4     # also ask Groq for 4 citations
"""

import argparse
import json
import shutil
from pathlib import Path

from finlint import storage
from finlint.api.views import (
    approvals_body,
    files_body,
    history_body,
    inspect_cell,
    run_body,
)
from finlint.db.store import SCHEMA, load_history, save_run
from finlint.graph.build import build_graph
from finlint.parsing.formula import make_ref
from finlint.parsing.reader import read_workbook
from finlint.pipeline import check_file
from finlint.rag.store import connect

WORKBOOK = Path("data/seed_models/Financial_Models.xlsx")
OUT = Path("web/public/fixtures")


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

    # Checked from its stored copy, exactly as an upload is, so the live API
    # can open this version again for the inspector and the size figures.
    stored = storage.store(WORKBOOK.read_bytes(), WORKBOOK.name)
    name = stored.name
    result = check_file(str(stored))

    # This run is always stored, so the latest version IS what the current code
    # found. Reusing older stored runs made run.json describe old rules while
    # stats, cells and explanations described new ones. A second copy is added
    # only on a first export, so history has two versions to compare.
    save_run(conn, result)
    if len(load_history(conn, name)) < 2:
        save_run(conn, result)

    workbook = read_workbook(str(stored))
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
