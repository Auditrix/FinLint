# Week 5 status (15 October 2026)

## What works

`scripts/check_agents.py` reads a workbook, runs the fixed rules, searches the
local corpus, asks the Standards and Auditor agents, and saves a JSON report.
It now also adds a plain-text written report. If the Auditor returns invalid
output, the finding stays in that report for human review instead of vanishing.

`guardrails/cells.py` checks a reported location against nonempty cells in the
parsed workbook. The Auditor uses that check, and the written report drops
locations that are not in the workbook. The Standards agent rejects an answer
that adds a cell address or URL in its own explanation, even if its quote is
real. The report takes its displayed locations from checked findings, never
from model prose.

`guardrails/injection.py` makes a workbook with a text cell telling the system
to report the file as clean. Its probe and tests show that the text does not
reach the Auditor's model prompt, the real finding stays visible, and the file
does not change. The fixture maker refuses to overwrite an existing workbook.
The report model sees only counts of findings, not raw workbook contents.
On 15 October, a live Groq probe of this text-cell attack kept the finding,
did not send the hostile text to the model, and left the workbook unchanged.

`agents/report.py` makes one model call for a short overview and templates the
finding details and source citations itself. It uses the title, page and URL
from the checked Standards result; the section label is not used because PDF
outlines can be coarser than the real page. An invalid or unavailable model
response falls back to fixed wording and cannot erase a finding. A citation
is presented as context for review, not proof that a cell is wrong.

For `data/seeds/Financial_Models.xlsx`, the tested finding is the real Excel
`#VALUE!` at `Beta computation!O307`. It is kept for human review. The final
run is in `data/generated/week5_error_cells_check_final.json`. This error is
kept by a fixed guardrail, with zero Auditor model calls.

The Standards agent now attaches one verified FASAB Handbook quote about
financial-reporting reliability. It labels this **contextual**, not a rule for
Excel or proof that this particular cell is wrong. Both tested Groq models
returned that quote; the final report uses Qwen. Before clarifying the prompt,
the stricter version returned no citation for this same example. The quote
checker still verifies the text against the stored document.

The deliberate hardcode fixture was checked with two Groq models. Both kept
it for review. Neither attached a citation after the prompt clarification,
so the more permissive wording did not bring back the unrelated passage in
these two trials. These are small examples, not a measured citation-precision
rate. The trial reports are in `data/generated/week5_hardcode_context_trial.json`
and `data/generated/week5_hardcode_gptoss_context_trial.json`.

## Measurements

- `scripts/evaluate_retrieval.py` checks 50 questions in
  `docs/retrieval_questions.tsv`. Each expected passage was checked against
  the 18,808 locally stored chunks before scoring. The exact target page or
  section was in the top 1 for 28/50, top 5 for 35/50, and top 10 for 41/50.
  The right document was in the top 1 for 39/50 and top 5 for 47/50. The
  detailed misses are in `data/generated/week5_retrieval_50.json`.
- This is a **known-passage** test: questions were written after looking at
  documents in the corpus. It measures whether search can recover those
  passages, not blind performance on new questions. Another page can also
  contain a valid answer even when the exact target page is missed. The prompt
  clarification did not change the retriever or these scores.
- Before the safety fix, a live two-model probe discarded the detected formula
  drift in 4 of 8 trials. The models' reasons mostly recognized the hostile
  text but called Excel's `N("text")` a harmless comment. That is a lost
  warning, not proof the models obeyed the injected instructions.
- The Auditor now keeps formula-drift findings containing text, Excel error
  cells, circular references, and broken links for human review without
  asking a model to discard them. It also hides raw finding messages, text
  values, quoted formula text, and quoted sheet names from agent prompts.
  `scripts/probe_agent_safety.py` confirms that four real hostile workbooks
  are read, detected, kept, and unchanged, with zero model calls. The local
  report is `data/generated/week5_formula_safety.json`.
- Previous live investment-advice and invented-location probes were rejected.
  Unit tests also reject invented quotes. These examples do not prove
  resistance to every wording or future model.
- The local full test suite with PostgreSQL running: 191 passed. New tests use
  a real small `.xlsx` file through the reader, rules, both agents and report.
  They use a fake model and source hit so they do not need network access. The warnings
  are from openpyxl's use of deprecated Python datetime calls.
- A live run of `scripts/check_agents.py` on `Financial_Models.xlsx` found
  `Beta computation!O307`, kept it without an Auditor model call, checked one
  contextual FASAB citation, and wrote a report. The local output is
  `data/generated/week5_agent_report_live.json`. The report includes the
  source title, page and URL, and omits the unreliable section label.

## Keep or rewind

Keep the safety checks and the narrow prompt clarification. The tested formula
warning is no longer dismissible by the model, the real Excel error stays
flagged, and one real but general quote is available with an honest context
label. Do not claim that retrieval improved or that the citation establishes
a spreadsheet rule. A broader evaluation could still change this decision.

## Agreed follow-ups

- The corpus lacks broadly applicable, spreadsheet-specific guidance for
  several rules. A candidate is the public U.S. GAO
  [Cost Estimating and Assessment Guide](https://www.gao.gov/products/gao-20-195g).
  Its chapter on validating cost estimates explicitly discusses checking
  spreadsheet formulas and data inputs. It is about **cost estimates**, so it
  should not be presented as a universal accounting rule. Nara agreed to add
  it and owns corpus ingestion; this local work did not re-ingest documents.
- The shared rule-to-question mapping and search ranking are Nara's files.
  With Nara's agreement, the Standards agent now sees five hits per search.
  This does not change the retriever's ranking, and target passages at ranks
  7 to 10 still need better queries or a separate retrieval change.
- The 50-question diagnostic is not a blind holdout, and four hostile formula
  wordings are not a comprehensive security evaluation. Report both limits
  in the final review.
- The new report path has a live PostgreSQL and Groq check on one real finding.
  This is a smoke test, not evidence that every rule or workbook will work.

## Reproduce

Run these with the project Python environment from the repository root after
starting PostgreSQL and loading the corpus. Live agent checks also need
`GROQ_API_KEY` in the ignored `.env`.

For Nara's pipeline, `write_report(workbook, reviewed_findings,
standards_by_cell, complete)` returns plain text. The mapping is keyed by
`(finding.sheet, finding.coordinate)` and should contain the result of
`explain_with_retriever` for each finding. The report does not retrieve or
verify new quotes itself.

```powershell
python scripts/ingest_corpus.py
python scripts/evaluate_retrieval.py
python scripts/probe_agent_safety.py
python scripts/check_agents.py --workbook data/seeds/Financial_Models.xlsx --rule error_cells --output data/generated/week5_error_cells_check_final.json
python -m pytest -q
```
