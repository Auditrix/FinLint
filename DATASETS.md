# FinLint dataset manifest

This file records every dataset the project uses: where it comes from, its licence, what job it does, and (once downloaded) its checksum. The full research notes behind these choices are in `CLAUDE.md`, Section 6.

**Storage policy (decided 3 September 2026):**
- The master copy of all data lives in the shared Google Drive folder `FinLint-data` (subfolders: `raw`, `seeds`, `testonly`, `corpus`, `generated`).
- Locally, data lives under `data/` inside the repo, which is in `.gitignore` and is never committed.
- The only committed data is tiny hand built test fixture workbooks in `tests/fixtures/`.
- `scripts/download_data.py` fetches what it can from original sources and verifies checksums.

**The four groups do four different jobs. Only Group 3 is for training.**

---

## Group 1: Seed models (clean models we break on purpose)

| Dataset | Source | Licence | Status |
|---|---|---|---|
| Fisy forecast model | `github.com/Emanuel-Allely/Fisy` | CC0-1.0 (public domain) | not downloaded |
| catherman Financial-Model-Analysis | `github.com/catherman/Financial-Model-Analysis` | MIT | not downloaded |
| EUSES spreadsheet corpus (financial category plus 576 seeded single fault versions) | Zenodo | CC BY 4.0 | not downloaded |

Notes: Fisy is the primary seed (in French, needs translation). Provenance warning from research: an MIT licence file added by an uploader who did not own the spreadsheet does not make it MIT. Fisy is the only one verified from its own README.

## Group 2: Outside answer key (TEST ONLY, never tune against these)

| Dataset | Source | Licence | Status |
|---|---|---|---|
| ExceLint-core annotations (70 workbooks, 700 labelled bug cells) | `github.com/ExceLint/ExceLint-core`, branch `master`, `test/annotations-processed.json` plus `test/subjects_xlsx/` | Apache 2.0 | not downloaded |
| Enron Error Corpus (36 human confirmed faults) | TU Graz, `Error_ENRON.zip` | Open | not downloaded |
| Enron spreadsheet corpus (15,770 real spreadsheets) | figshare | CC BY 4.0 | not downloaded |
| Spreadsheet Arena (765 real LLM generated workbooks) | Spreadsheet Arena | CC BY-NC 4.0 | not downloaded |
| SpreadsheetBench v2 | GitHub | MIT | not downloaded |

Rule: these are used exactly once, at Tier 2 and Tier 3 evaluation time, with the detector untouched and untuned. Tuning against them would make the evaluation circular.

## Group 3: Training data (the ML chapter)

**VynFi journal entries, 1 million line version.**

- Source: `huggingface.co/datasets/VynFi/vynfi-journal-entries-1m`
- Licence: Apache 2.0
- Status: **downloaded** to `data/training/vynfi/` and mirrored to Drive `raw/vynfi/`
- Content: 667,584 journal entry lines, 48 fields, real header and line structure with true `debit_amount` and `credit_amount`, posting dates, cost centres, plus `is_fraud` and `is_anomaly` labels.
- Important wording rule: the dataset is tagged **Synthetic**. In every write up say "realistic synthetic journal entries", never "real transactions".
- `chart_of_accounts.parquet` carries `normal_debit_balance`, `is_suspense_account`, `is_control_account`, and typical amount ranges. These also feed the deterministic accounting checks later, not just the ML chapter.
- Remote layout note: on HuggingFace the three train shards sit under `data/`, the other files sit at the repo root, and there is also a `star_schema/` folder (CSV versions) we do not download.

SHA256 checksums of the downloaded files (verified 7 September 2026):

| File | SHA256 | Bytes |
|---|---|---|
| `train-00000-of-00003.parquet` | `d78447002c8cda6e9702f9025cea36778c0bbd8c6317d41f8ceb5ef872d2a40c` | 10,706,197 |
| `train-00001-of-00003.parquet` | `ece05556ee41884468930d23069cdcdf58060362ee632e85343b5a1a0f0305eb` | 9,476,568 |
| `train-00002-of-00003.parquet` | `47a3bc91d5471eb51fa1cba43ab20cb6e2b384d0fe366097a018d257b8b8d1c9` | 13,908,055 |
| `chart_of_accounts.parquet` | `76298bfa2acfe2f25490b4cf3dcc88d1e5b90701e95b1afe562d436d0a2d9c5f` | 31,314 |
| `cost_centers.parquet` | `39524895e894f15822c76ffca565ea91217673258ed165c97c9d8136433e9495` | 6,977 |
| `profit_centers.parquet` | `1e075cd64fbeb2d87eb6360c18829b1cf36dcec7dbab9181df2a04d8cb1f2249` | 6,973 |
| `je_network.parquet` | `a23f5cfabc97a10cc375925265dc0466e52472feedf1c4e45c662d9c464682e2` | 5,942,966 |
| `trial_balances.parquet` | `c67e89a201bfaf17398eb4fd2cf41e23effc86816315aac34abda48de63063a0` | 179,000 |

Load the three train shards and stack them. `je_network.parquet` has the fraud type column.

**Do not use** `GitiHubi/deepAI` fraud datasets (derived from mobile money data, renamed to look like ERP data) or `aanshshah/gaap-sec-compliance-dataset` (relicensed copyrighted FASB text). Reasons in `CLAUDE.md`, Sections 4.1 and 6.3.

## Group 4: RAG corpus (search material, not training) — all public domain

RAG stands for Retrieval Augmented Generation, meaning the AI searches these documents and quotes what it finds. All are US government works, which carry no copyright under 17 U.S.C. § 105.

| Document | URL | Status |
|---|---|---|
| GAO Financial Audit Manual Vol 1 | `gao.gov/assets/gao-26-108577.pdf` | not downloaded |
| GAO Financial Audit Manual Vol 2 | `gao.gov/assets/gao-26-107706.pdf` | not downloaded |
| GAO Financial Audit Manual Vol 3 | `gao.gov/assets/gao-26-108632.pdf` | not downloaded |
| FASAB Handbook 2025 | `files.fasab.gov/pdffiles/2025_FASAB_Handbook.pdf` | not downloaded |
| Treasury USSGL Part 1 | `tfx.treasury.gov/system/files/2026-01/p1-combined-2026.pdf` | not downloaded |
| SEC Financial Reporting Manual | `sec.gov/files/cf-frm.pdf` | not downloaded |
| GAO Yellow Book 2024 | `gao.gov/assets/d24106786.pdf` | not downloaded |
| GAO Green Book 2025 | `gao.gov/assets/gao-25-107721.pdf` | not downloaded |
| OMB Circular A-136 | `whitehouse.gov/wp-content/uploads/2026/05/OMB-Circular-No.-A-136-2026.pdf` | not downloaded |
| Reg S-X and S-K (Title 17 eCFR XML) | `govinfo.gov/bulkdata/ECFR/title-17/ECFR-title17.xml` | not downloaded |
| XBRL US Data Quality Committee rules | `github.com/DataQualityCommittee/dqc_us_rules` | not downloaded |

Hard rule: **no FASB or IFRS text anywhere in the corpus.** Both bodies ban AI use of their content in their terms of use. Details in `CLAUDE.md`, Section 4.1.

SEC access rule: any request to `sec.gov` must send a `User-Agent` header of the form `Name email`, and stay under 10 requests per second. The download script reads the contact string from the `SEC_USER_AGENT` environment variable (see `.env.example`).
