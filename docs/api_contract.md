# FinLint API contract

The agreement between `src/finlint/api/main.py` (Nara) and the frontend in
`web/` (built against this file). Same rule as `Page`, `Chunk` and `Finding`:
**frozen once agreed, and neither side changes it alone.**

The TypeScript mirror of every shape below lives in `web/lib/types.ts`. If the
two ever disagree, this file wins and `types.ts` is wrong.

A working reference for every response, computed from the real backend, is
`scripts/export_ui_fixture.py`. It builds exactly these JSON shapes from
`pipeline`, `graph`, `db.store` and `lineage.diff`, so it is the quickest way
to see what each endpoint must return.

---

## Before you start

FastAPI needs **`python-multipart`** to accept an uploaded file, and it is not
installed yet. Add `"python-multipart>=0.0.9"` to the dependencies in
`pyproject.toml`, then `pip install -e .`. Without it, `POST /api/check` fails
on import with a message about form data.

## Conventions

- **Base path** `/api`. In development the frontend calls
  `http://localhost:8000`; set `NEXT_PUBLIC_API_BASE` to change it.
- **CORS** must allow `http://localhost:3000` in development.
- **Times** are ISO 8601 strings **in UTC**, for example
  `2026-10-24T08:18:34.644220+00:00`. The frontend converts to local time.
- **A file name** in a path is URL encoded, for example
  `Financial_Models.xlsx`. It is `Path(path).name`, the same identity
  `db.store.save_run` uses, never a full path.
- **A cell reference** is `Sheet!A1`, built by `parsing.formula.make_ref`.
  Sheet names can contain spaces, so it is always URL encoded.
- **Cell values** are `string | number | boolean | null`. Dates and times
  become ISO strings.
- **Errors** return a non 2xx status with `{"detail": "plain words"}`. The
  frontend shows `detail` to the user, so write it for a person.
- **Signing in.** Every endpoint except `GET /api/health` and
  `POST /api/auth/login` needs the `finlint_session` cookie. Without it the
  answer is `401`. A role that may not do something gets `403` with the
  reason. The frontend sends the cookie with `credentials: "include"`.
- **Rate limits** answer `429` with a `Retry-After` header in seconds and a
  `detail` saying how long to wait. The limits are listed in `api/main.py`.
- **Roles** (`finlint/auth.py`): `analyst` uploads and reads; `reviewer`
  also marks findings as intentional; `signer` only reads.

---

## Shared shapes

```text
Severity       "critical" | "high" | "medium" | "low"

Finding        rule_id, severity, sheet, coordinate, message, blast_radius
               exactly rules.model.Finding

AnnotatedFinding  a Finding plus:
               status      "new" | "still_there"   from lineage.diff.diff_runs
               first_seen  int | null              from lineage.diff.first_seen
               approved    bool                    finding_key(f) in load_approvals
```

`status` compares the latest run to the one before it. On a file's first
version every finding is `"new"`.

---

## Endpoints

### `GET /api/health`

Lets the UI say what is connected, and switch off the AI buttons when there
is no key rather than letting them fail.

```json
{ "ok": true, "database": true, "llm": true, "version": "0.1.0" }
```

`llm` is true when `GROQ_API_KEY` is set. `database` is true when `connect()`
succeeds.

### `POST /api/auth/login`

```json
{ "username": "nara", "password": "..." }
```

Sets the session cookie (HttpOnly, SameSite=Lax, 12 hours) and returns the
`Account`:

```json
{ "username": "nara", "role": "reviewer", "can_upload": true, "can_decide": true }
```

A wrong name and a wrong password get the same `401`, so the answer does not
reveal which names exist. Five wrong passwords for one name from one address
in 15 minutes gives `429`.

### `POST /api/auth/logout`

Deletes the session on the server and clears the cookie. `{"ok": true}`.

### `GET /api/auth/me`

The `Account` signed in, or `401`. When no account exists at all, the `401`
detail says how to create one.

### `GET /api/files`

Every workbook ever checked, newest first.

```json
[
  {
    "name": "Financial_Models.xlsx",
    "latest_version": 2,
    "latest_score": 100,
    "latest_at": "2026-10-24T08:18:34+00:00",
    "finding_count": 1466
  }
]
```

### `POST /api/check`

Analysts and reviewers only. Ten per minute per person.

`multipart/form-data` with one field, `file`, the `.xlsx`.

Store the uploaded bytes (this is the Week 6 file storage task), run
`pipeline.check_file` on them with no model, `save_run` the result, then
return the same body as `GET /api/files/{name}/run`.

Reject anything that is not `.xlsx` or `.xlsm` with a 400 and a readable
`detail`. FinLint never writes to the uploaded file.

### `GET /api/files/{name}/run`

The latest run of one file, ready to render. This is the main call.

```json
{
  "file": "Financial_Models.xlsx",
  "run_id": 4,
  "version": 2,
  "previous_version": 1,
  "created_at": "2026-10-24T08:18:34+00:00",
  "sha256": "ca90edfab653...",
  "unchanged_since_previous": true,
  "score": 100,
  "stats": { "sheets": 22, "cells": 7986, "formulas": 3887, "links": 18790 },
  "findings": [ AnnotatedFinding, ... ],
  "resolved": [ Finding, ... ]
}
```

- `findings` keep the engine's order, which is already worst first.
- `resolved` is `diff_runs(previous, current).resolved`: findings that were in
  the previous version and are gone now. Empty on a first version.
- `unchanged_since_previous` is `sha256 == previous run's sha256`.
- `stats.links` is the total number of edges, `sum(len(v) for v in graph.feeds.values())`.

### `GET /api/files/{name}/history`

Every version, oldest first. Feeds the score trend and the version list.

```json
[
  {
    "version": 1,
    "run_id": 3,
    "created_at": "2026-10-24T08:18:34+00:00",
    "score": 100,
    "sha256": "ca90edfab653...",
    "counts": { "critical": 27, "high": 632, "medium": 0, "low": 807 },
    "total": 1466
  }
]
```

### `GET /api/files/{name}/cell?ref=Sheet!A1`

Everything the inspector shows for one cell. Built from the workbook and the
graph, so keep both in memory per file rather than re-reading the workbook on
every click.

```json
{
  "ref": "DCF Analysis!E12",
  "sheet": "DCF Analysis",
  "coordinate": "E12",
  "formula": "=E10*(1-E11)",
  "value": 1530.4,
  "number_format": "#,##0.0",
  "precedents": ["DCF Analysis!E10", "DCF Analysis!E11"],
  "precedents_total": 2,
  "dependents": ["DCF Analysis!E14"],
  "dependents_total": 1,
  "blast_radius": 6,
  "row": [
    { "coordinate": "D12", "formula": "=D10*(1-D11)", "value": 1490.2,
      "shape": "=#*(1-#)", "is_target": false },
    { "coordinate": "E12", "formula": "=E10*(1-E11)", "value": 1530.4,
      "shape": "=#*(1-#)", "is_target": true }
  ],
  "row_total": 14,
  "majority_shape": "=#*(1-#)",
  "majority_count": 12,
  "formula_count": 13
}
```

- `precedents` is `graph.analyse.precedents`, what this cell **reads**.
- `dependents` is `graph.analyse.dependents`, what **reads this cell**.
- **Cap both lists at 50**, sorted, and send the true size in `*_total`. One
  `SUM` over a whole column would otherwise send thousands of references.
- `blast_radius` is `len(graph.analyse.blast_radius(graph, ref))`.
- `row` is the non empty cells of the same row, left to right, **at most 8
  either side of the target**. `row_total` is the full count. `shape` is
  `rules.checks.REFERENCE.sub("#", formula)`, or `null` for a typed value.
  Computing it server side keeps one definition of "shape".
- `majority_shape` is the most common non null `shape` across the **whole**
  row, computed before the window is cut, so it is the same comparison
  `formula_drift` made. `null` when the row has no formulas.
- `majority_count` is how many cells in the **whole** row have that shape, and
  `formula_count` how many cells in the whole row hold a formula. Both are
  counted before the window is cut: counting only the cells shown would
  under-report on any row wider than the window.
- Unknown sheet or cell returns 404.

### `POST /api/explain`

Ask the Standards agent for one finding. One finding per call on purpose: it
costs 1 to 3 Groq calls, and the free tier allows 30 a minute.

Request:

```json
{ "file": "Financial_Models.xlsx", "finding": Finding }
```

Response, exactly `agents.standards.StandardsResult`:

```json
{
  "supported": true,
  "explanation": "Context only; the citation does not prove this cell is wrong. ...",
  "citations": [
    {
      "source": "gao_cost_estimating_2020.pdf",
      "title": "GAO Cost Estimating and Assessment Guide (GAO-20-195G, March 2020)",
      "url": "https://www.gao.gov/assets/d20195G.pdf",
      "page": 185,
      "section": "Process Tasks",
      "quote": "the documentation allows someone to trace the data, calculations..."
    }
  ],
  "evidence_scope": "contextual"
}
```

When no key is set, return 503 with a readable `detail`. `supported: false`
with no citations is a valid, honest answer, not an error.

### `GET /api/files/{name}/approvals`

Every human decision on this file, newest first. **Every row**, including two
decisions on one cell: this is the audit trail.

```json
[
  {
    "rule_id": "hardcoded_value",
    "sheet": "Model",
    "coordinate": "C15",
    "reason": "Deliberate, locked by policy",
    "decided_by": "nara",
    "decided_at": "2026-10-24T09:01:12+00:00"
  }
]
```

`db.store.load_approvals` returns only the set of keys, so this endpoint needs
its own `SELECT` returning the full rows.

### `POST /api/approvals`

Mark a finding as intentional.

```json
{ "file": "Financial_Models.xlsx", "finding": Finding,
  "reason": "Deliberate, locked by policy" }
```

Reviewers only (`403` otherwise). The decider is always the account signed
in; a `who` field, if sent, is ignored, so nobody can record a decision under
another name. Call `db.store.approve`. It already refuses an unknown file, a
finding that was never reported, and a blank reason, all with `ValueError`.
Turn that into a 400 and pass the message through as `detail`. Return the
stored `Approval`.

### `GET /api/evaluation`

The measured results, for the Evaluation view. Serve
`docs/evaluation.json` as it is. Every number in it is from the README and
names the script that produced it.
