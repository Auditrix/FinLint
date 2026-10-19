# FinLint — Session Handoff (as of 3 September 2026)

> **How to use this file:** in a new Claude chat, attach BOTH files together:
> 1. `finlint_fin` (the full project context: constraints, tech stack, datasets, architecture, plan)
> 2. this file (decisions made and progress so far)
> The context file is the source of truth for WHAT the project is. This file records WHERE WE ARE.

---

## 1. The project in three lines

FinLint is a linter for AI made financial spreadsheets. It reads an Excel model, finds mistakes deterministically, explains each one in plain words, cites a real accounting rule from a public domain government corpus, and keeps a permanent record. It never fixes anything by itself, a human always decides.

Team of 2: **Narayanan (Nara)** and **Sowb**. Timeline 1 September to 20 October 2026. College review checkpoint: **11 September 2026**. This is a learning and portfolio project, not a startup.

## 2. Rules Claude must follow (from the context file, strictly enforced)

- **Tier A code (human types every line, Claude must NOT write it):** dependency map, every rule check, ML training loop, agent orchestration, evaluation harness, guardrails. Claude reviews and explains only.
- **Tier B (Claude may draft, humans rewrite):** FastAPI endpoints, DB models, storage, vector search plumbing, auth.
- **Tier C (Claude writes freely):** Streamlit UI, React page, Dockerfile, CI config, download scripts, Colab setup snippets.
- **Style:** simple plain English, short sentences, NEVER use dashes in prose (em, en, or double hyphen), define every abbreviation on first use.
- Do not relitigate the tech stack or the hard constraints (no pycel, no FASB or IFRS text anywhere, openpyxl plus the `formulas` library, pgvector, Streamlit first).

## 3. Decisions made in the first working session (3 Sep 2026)

1. **Team split model chosen:** split by component, each person owns components end to end. Every change goes through a pull request reviewed by the other person. Thirty minute weekly teach back. **One swap at the end of Week 4** so both touch both halves. Person 1 (stronger Python) takes the graph track, Person 2 takes the detector and agent track. Full week by week table was drawn up (Week 1: one does data pipeline plus evaluation harness, other does Benford plus PyOD detectors, autoencoder is the weekend stretch goal).
2. **Rule pack format:** YAML, because it allows comments and each rule should carry a note about why it exists.
3. **Name:** FinLint confirmed, stays.
4. **Recalculation test moved earlier:** the test of whether `formulas` can recalculate an openpyxl written workbook should be run THIS week as a one hour de risking spike, not waiting for Week 2 day 1. (Not yet done as of this handoff.)
5. **Data storage architecture:** one shared Google Drive folder holds all data. GitHub holds all code plus a `DATASETS.md` manifest (source, URL, licence, checksum per dataset) plus a download script. `data/` is in `.gitignore`, never committed. Tiny test fixture workbooks are the only committed data. Rejected: Git LFS (bandwidth limits), DVC (overkill for 7 weeks).
6. **Colab policy:** Google Colab is needed only 2 or 3 times total (Week 1 autoencoder training, Week 5 embedding generation for the corpus). Everything else runs on laptops. Notebook discipline: real logic lives in `.py` files in the repo, notebooks are thin drivers, each person works in their OWN notebook, clear outputs before committing, API keys go in Colab Secrets never in cells.
7. **Fault corpus sharing:** commit the generator code plus a fixed random seed, not the output files. The corpus regenerates identically.

## 4. Progress so far (done items)

- [x] GitHub organisation created by Narayanan, both members are admin. (Repo itself NOT yet created.)
- [x] Shared Drive folder **`FinLint-data`** created by Sowb, Narayanan added as editor. Subfolders: `raw`, `seeds`, `testonly`, `corpus`, `generated`.
- [x] **VynFi dataset downloaded and uploaded to `raw/vynfi/`** (8 parquet files, ~38 MB): `train-00000/00001/00002-of-00003.parquet` (main journal entries in 3 shards, load all three and stack), `chart_of_accounts.parquet`, `cost_centers.parquet`, `profit_centers.parquet`, `trial_balances.parquet`, `je_network.parquet` (has the fraud type column).
- [x] Update note sent to Narayanan about the Drive setup.

## 5. Useful facts learned along the way

- The VynFi dataset page confirms: Apache 2.0, 667,584 rows, 75.3 MB listed on site (the extra beyond the train shards is the star_schema folder). It is tagged **Synthetic**, so in all write ups say "realistic synthetic journal entries", never "real transactions". This honesty matters for reviewers.
- `chart_of_accounts.parquet` contains `normal_debit_balance` (which side each account normally sits on), `is_suspense_account`, `is_control_account`, and typical amount ranges. These fields will also feed the deterministic accounting checks later, not just the ML chapter.
- HuggingFace needs no account to download this dataset.

## 6. Immediate next steps (in order)

1. **Create the `finlint` repository in the GitHub org** with the skeleton: folder layout, `.gitignore` (with `data/`), `DATASETS.md` manifest built from Section 6 of the context file, `scripts/download_data.py`, the standard Colab setup cell snippet, and the context file saved as `CLAUDE.md` in the repo root. All Tier C, Claude writes these.
2. **Run the recalculation spike** (one hour): install `formulas`, write a five cell workbook with openpyxl, recalculate, check the answer. If it fails, fall back plan is headless LibreOffice with `OOXMLRecalcMode` set to 0.
3. **Start Week 1 ML work** on the VynFi data: load the 3 shards, explore the 48 fields, train and test split, then Benford, Isolation Forest, ECOD, and the autoencoder as stretch. The training loop and evaluation harness are Tier A (humans write, Claude reviews).
4. **Prepare the 11 September checkpoint demo:** a precision and recall comparison table of the four methods, shown in a Streamlit page (Streamlit page is Tier C, Claude writes).

## 7. Environment notes

- Sowb works on Windows 11, files land in `C:\Users\svgow\Downloads`.
- Working sessions so far ran in Claude Code desktop app with no project folder. Once the repo exists, open the session IN the repo folder so `CLAUDE.md` loads automatically.
