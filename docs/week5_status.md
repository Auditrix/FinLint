# Week 5 status (14 October 2026)

## What works

`scripts/check_agents.py` reads a workbook, runs the fixed rules, searches the
local corpus, asks the Standards and Auditor agents, and saves a JSON report.
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
- `python -m pytest -q` in the project environment: 175 passed. The warnings
  are from openpyxl's use of deprecated Python datetime calls.

## Keep or rewind

Keep the safety checks and the narrow prompt clarification. The tested formula
warning is no longer dismissible by the model, the real Excel error stays
flagged, and one real but general quote is available with an honest context
label. Do not claim that retrieval improved or that the citation establishes
a spreadsheet rule. A broader evaluation could still change this decision.

## Still needs a team decision

- The corpus lacks broadly applicable, spreadsheet-specific guidance for
  several rules. A candidate is the public U.S. GAO
  [Cost Estimating and Assessment Guide](https://www.gao.gov/products/gao-20-195g).
  Its chapter on validating cost estimates explicitly discusses checking
  spreadsheet formulas and data inputs. It is about **cost estimates**, so it
  should not be presented as a universal accounting rule. Nara owns corpus
  ingestion; add it only after agreeing on source scope and metadata.
- The shared rule-to-question mapping and search ranking are Nara's files.
  The Standards agent currently sees two hits from each search. Some target
  passages in the 50-question diagnostic were only at ranks 7 to 10. Agree whether to
  change query wording, candidate count, or the corpus before editing the
  shared retrieval interface.
- The 50-question diagnostic is not a blind holdout, and four hostile formula
  wordings are not a comprehensive security evaluation. Report both limits
  in the final review.

## Reproduce

Run these with the project Python environment from the repository root after
starting PostgreSQL and loading the corpus. Live agent checks also need
`GROQ_API_KEY` in the ignored `.env`.

```powershell
python scripts/ingest_corpus.py
python scripts/evaluate_retrieval.py
python scripts/probe_agent_safety.py
python scripts/check_agents.py --workbook data/seeds/Financial_Models.xlsx --rule error_cells --output data/generated/week5_error_cells_check_final.json
python -m pytest -q
```
