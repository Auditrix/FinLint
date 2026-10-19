"""Download FinLint datasets from their original sources.

Usage:
    python scripts/download_data.py               # VynFi training data only (the default)
    python scripts/download_data.py --group rag   # the government document corpus
    python scripts/download_data.py --group all   # everything this script knows how to fetch

Every file lands under data/, which is gitignored. The manifest with licences
and checksums is DATASETS.md in the repo root. Seed models and the outside
test corpora (Groups 1 and 2) are not automated yet; run with --group seeds
to print where to get them by hand.
"""

import argparse
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# Group 3: VynFi journal entries (Apache 2.0). See DATASETS.md.
# Remote layout: the three train shards sit under data/ on HuggingFace,
# everything else sits at the dataset root. We flatten locally.
VYNFI_BASE = "https://huggingface.co/datasets/VynFi/vynfi-journal-entries-1m/resolve/main/"
VYNFI_DIR = DATA_DIR / "training" / "vynfi"
VYNFI_FILES = {
    # remote path: (local filename, expected sha256)
    "data/train-00000-of-00003.parquet": (
        "train-00000-of-00003.parquet",
        "d78447002c8cda6e9702f9025cea36778c0bbd8c6317d41f8ceb5ef872d2a40c",
    ),
    "data/train-00001-of-00003.parquet": (
        "train-00001-of-00003.parquet",
        "ece05556ee41884468930d23069cdcdf58060362ee632e85343b5a1a0f0305eb",
    ),
    "data/train-00002-of-00003.parquet": (
        "train-00002-of-00003.parquet",
        "47a3bc91d5471eb51fa1cba43ab20cb6e2b384d0fe366097a018d257b8b8d1c9",
    ),
    "chart_of_accounts.parquet": (
        "chart_of_accounts.parquet",
        "76298bfa2acfe2f25490b4cf3dcc88d1e5b90701e95b1afe562d436d0a2d9c5f",
    ),
    "cost_centers.parquet": (
        "cost_centers.parquet",
        "39524895e894f15822c76ffca565ea91217673258ed165c97c9d8136433e9495",
    ),
    "profit_centers.parquet": (
        "profit_centers.parquet",
        "1e075cd64fbeb2d87eb6360c18829b1cf36dcec7dbab9181df2a04d8cb1f2249",
    ),
    "je_network.parquet": (
        "je_network.parquet",
        "a23f5cfabc97a10cc375925265dc0466e52472feedf1c4e45c662d9c464682e2",
    ),
    "trial_balances.parquet": (
        "trial_balances.parquet",
        "c67e89a201bfaf17398eb4fd2cf41e23effc86816315aac34abda48de63063a0",
    ),
}

# Group 4: RAG corpus, all US government public domain documents.
# No pinned checksums: agencies reissue these PDFs at the same URL,
# so we record the size on disk instead and trust HTTPS.
RAG_DIR = DATA_DIR / "rag_corpus"
RAG_FILES = {
    "https://www.gao.gov/assets/gao-26-108577.pdf": "gao_financial_audit_manual_vol1.pdf",
    "https://www.gao.gov/assets/gao-26-107706.pdf": "gao_financial_audit_manual_vol2.pdf",
    "https://www.gao.gov/assets/gao-26-108632.pdf": "gao_financial_audit_manual_vol3.pdf",
    "https://files.fasab.gov/pdffiles/2025_FASAB_Handbook.pdf": "fasab_handbook_2025.pdf",
    "https://tfx.treasury.gov/system/files/2026-01/p1-combined-2026.pdf": "ussgl_part1_2026.pdf",
    "https://www.sec.gov/files/cf-frm.pdf": "sec_financial_reporting_manual.pdf",
    "https://www.gao.gov/assets/d24106786.pdf": "gao_yellow_book_2024.pdf",
    "https://www.gao.gov/assets/gao-25-107721.pdf": "gao_green_book_2025.pdf",
    "https://www.whitehouse.gov/wp-content/uploads/2026/05/OMB-Circular-No.-A-136-2026.pdf": "omb_circular_a136_2026.pdf",
    "https://www.govinfo.gov/bulkdata/ECFR/title-17/ECFR-title17.xml": "ecfr_title17_reg_sx_sk.xml",
}

SEEDS_NOTE = """\
Groups 1 and 2 are fetched by hand for now (archives and repos, not single files):
  Fisy (CC0):            https://github.com/Emanuel-Allely/Fisy
  catherman (MIT):       https://github.com/catherman/Financial-Model-Analysis
  EUSES (CC BY 4.0):     search Zenodo for the EUSES spreadsheet corpus
  ExceLint annotations:  https://github.com/ExceLint/ExceLint-core (branch master, test/)
  Enron Error Corpus:    TU Graz, Error_ENRON.zip
  Spreadsheet Arena:     CC BY-NC 4.0, see DATASETS.md
Put them in the shared Drive folder FinLint-data and under data/ locally.
"""


def user_agent() -> str:
    """SEC requires a User-Agent of the form 'Name email'. Set SEC_USER_AGENT
    in your .env (see .env.example) or in the shell."""
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        pass
    contact = os.environ.get("SEC_USER_AGENT")
    if not contact:
        print("WARNING: SEC_USER_AGENT is not set. sec.gov may refuse the request.")
        contact = "FinLint student project"
    return contact


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(request, timeout=120) as response, open(tmp, "wb") as out:
        while True:
            block = response.read(1 << 20)
            if not block:
                break
            out.write(block)
    tmp.replace(dest)


def download_vynfi() -> bool:
    ok = True
    for remote, (local_name, expected) in VYNFI_FILES.items():
        dest = VYNFI_DIR / local_name
        if dest.exists() and sha256_of(dest) == expected:
            print(f"  ok (already present): {local_name}")
            continue
        print(f"  downloading: {local_name}")
        fetch(VYNFI_BASE + remote, dest)
        actual = sha256_of(dest)
        if actual != expected:
            print(f"  CHECKSUM MISMATCH for {local_name}")
            print(f"    expected {expected}")
            print(f"    got      {actual}")
            print("    The upstream dataset may have changed. Check DATASETS.md before using it.")
            ok = False
        else:
            print(f"  verified: {local_name}")
    return ok


def download_rag() -> bool:
    ok = True
    for url, local_name in RAG_FILES.items():
        dest = RAG_DIR / local_name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"  ok (already present): {local_name}")
            continue
        print(f"  downloading: {local_name}")
        try:
            fetch(url, dest)
            print(f"  saved: {local_name} ({dest.stat().st_size:,} bytes)")
        except Exception as error:
            print(f"  FAILED: {local_name}: {error}")
            ok = False
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=["vynfi", "rag", "seeds", "all"], default="vynfi")
    args = parser.parse_args()

    ok = True
    if args.group in ("vynfi", "all"):
        print("Group 3: VynFi journal entries")
        ok = download_vynfi() and ok
    if args.group in ("rag", "all"):
        print("Group 4: government RAG corpus")
        ok = download_rag() and ok
    if args.group in ("seeds", "all"):
        print(SEEDS_NOTE)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
