"""Turn the downloaded reference documents into clean text, one record per page.

The corpus lives in data/rag_corpus and is every document the Standards agent is
allowed to quote. All of it is US government work, which carries no copyright
under 17 U.S.C. 105, so we can redistribute it. CLAUDE.md Section 6.4 explains
why GAAP and IFRS text cannot be used here at all.

This file only ever reads. It never writes to a source document, which is the
same promise FinLint makes about a user's workbook.

The output of this file is the input to chunk.py. One Page is one page of one
document, not a search sized piece. Splitting comes later, because the embedding
model stops reading after 512 tokens and most of these pages are longer.
"""

import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pymupdf
from pydantic import BaseModel

# Where the downloaded documents live, relative to the repository root.
CORPUS_DIR = Path("data/rag_corpus")

# A page with less text than this is a cover, a divider or a blank, and an
# empty piece of text can never be a useful search result.
MIN_PAGE_CHARS = 50

# A line appearing on at least this share of a document's pages is a running
# header or footer, not content.
BOILERPLATE_SHARE = 0.5

# File name -> (readable title, source URL).
# The title is what a reader sees in a citation, so "GAO Yellow Book 2024" and
# never "gao_yellow_book_2024.pdf". The URL is how that reader checks the quote
# for themselves, which is the whole point of guardrail 1.
# Volume numbers were read off each cover page, not guessed.
CORPUS = {
    "gao_fam_vol1.pdf": (
        "GAO Financial Audit Manual Volume 1 (June 2026)",
        "https://www.gao.gov/assets/gao-26-108577.pdf",
    ),
    "gao_fam_vol2.pdf": (
        "GAO Financial Audit Manual Volume 2 (June 2026)",
        "https://www.gao.gov/assets/gao-26-107706.pdf",
    ),
    "gao_fam_vol3.pdf": (
        "GAO Financial Audit Manual Volume 3 (July 2026)",
        "https://www.gao.gov/assets/gao-26-108632.pdf",
    ),
    "fasab_handbook_2025.pdf": (
        "FASAB Handbook 2025",
        "https://files.fasab.gov/pdffiles/2025_FASAB_Handbook.pdf",
    ),
    "treasury_ussgl_part1_2026.pdf": (
        "Treasury USSGL Part 1 (2026)",
        "https://tfx.treasury.gov/system/files/2026-01/p1-combined-2026.pdf",
    ),
    "sec_financial_reporting_manual.pdf": (
        "SEC Financial Reporting Manual",
        "https://www.sec.gov/files/cf-frm.pdf",
    ),
    "gao_yellow_book_2024.pdf": (
        "GAO Yellow Book 2024 (Government Auditing Standards)",
        "https://www.gao.gov/assets/d24106786.pdf",
    ),
    "gao_green_book_2025.pdf": (
        "GAO Green Book 2025 (Internal Control Standards)",
        "https://www.gao.gov/assets/gao-25-107721.pdf",
    ),
    "omb_circular_a136_2026.pdf": (
        "OMB Circular A-136 (2026)",
        "https://www.whitehouse.gov/wp-content/uploads/2026/05/OMB-Circular-No.-A-136-2026.pdf",
    ),
    "ecfr_title17.xml": (
        "17 CFR (Regulation S-X and Regulation S-K)",
        "https://www.govinfo.gov/bulkdata/ECFR/title-17/ECFR-title17.xml",
    ),
}

# Characters a PDF uses for typesetting, mapped to the plain equivalent a person
# would type. Without this, a quote typed with a straight apostrophe never
# matches the document's curly one, and guardrail 1 throws away a correct
# citation.
NORMALISE = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "−": "-",
    " ": " ", "…": "...",
    "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
}

# A line that is only a page label, e.g. "Page 32". These repeat on every page
# but with a different number each time, so counting repeats cannot catch them.
PAGE_LABEL = re.compile(r"^Page\s+\d+(\s+of\s+\d+)?$", re.IGNORECASE)

# The section sign starting an eCFR section number, written "§ 210.1-01".
SECTION_SIGN = re.compile(r"^\s*§\s*")


class Page(BaseModel):
    """One page of one document, cleaned and ready to be chunked.

    Frozen shape, confirmed with Sowb. Change it only when we both agree.
    """

    source: str          # file name, e.g. "gao_yellow_book_2024.pdf"
    title: str           # readable name, what a citation shows the reader
    url: str             # where it came from, so the reader can verify it
    page: int | None     # PDF page number, 1 based. None for the eCFR XML,
                         # which has sections instead of pages.
    section: str | None  # nearest heading above this page. None on pages that
                         # come before the document's first heading.
    text: str            # the cleaned text of this page


def tidy(text: str) -> str:
    """Normalise one piece of text so a quote typed by hand can match it.

    citations.py must call this on the model's quote before searching, or the
    two sides end up normalised differently and real citations get rejected.
    """
    for fancy, plain in NORMALISE.items():
        text = text.replace(fancy, plain)
    text = re.sub(r"[ \t]+", " ", text)      # runs of spaces become one
    text = re.sub(r"\n{3,}", "\n\n", text)   # runs of blank lines become one
    return text.strip()


def _boilerplate(page_texts: list[str]) -> set[str]:
    """Lines repeating across most pages, which are headers and footers.

    Every page of the Yellow Book carries its chapter name and the report
    number "GAO-24-106786". Left in, those words sit in every chunk, and a
    search for them matches all 260 pages equally, which is as useless as
    matching none of them.
    """
    counts: Counter[str] = Counter()
    for text in page_texts:
        # A set per page, so a line repeated twice on one page still counts once.
        counts.update({line.strip() for line in text.splitlines() if line.strip()})

    # At least 3, so a two page document cannot call its only line boilerplate.
    cutoff = max(3, int(len(page_texts) * BOILERPLATE_SHARE))
    return {line for line, seen in counts.items() if seen >= cutoff}


def _strip_boilerplate(text: str, junk: set[str]) -> str:
    """Drop the running headers, footers and page labels from one page."""
    kept = [line for line in text.splitlines()
            if line.strip() not in junk and not PAGE_LABEL.match(line.strip())]
    return "\n".join(kept)


def _sections_by_page(outline: list[tuple[str, int]],
                      page_count: int) -> list[str | None]:
    """Map every page number to the heading it sits under.

    Returns a list indexed by 1 based page number, so sections[32] is the
    heading covering page 32. Index 0 is unused and always None.

    The rule is: a page belongs to the last heading that started at or before
    it. A page sitting before the first heading belongs to nothing, hence None.
    Three of our documents have no heading until page 2, 5 or 7, so None is
    normal here and not an error.
    """
    sections: list[str | None] = [None] * (page_count + 1)

    # First, mark the pages where a heading actually starts.
    for heading, page_num in outline:
        if 1 <= page_num <= page_count:
            sections[page_num] = heading

    # Then carry each heading forward across the pages that follow it.
    current = None
    for number in range(1, page_count + 1):
        if sections[number] is None:
            sections[number] = current
        else:
            current = sections[number]

    return sections


def read_pdf(path) -> list[Page]:
    """Read one PDF into a list of Page records, one per page worth keeping."""
    path = Path(path)
    title, url = CORPUS.get(path.name, (path.stem, ""))
    doc = pymupdf.open(path)

    # The outline is the document's own table of contents, a list of
    # [level, heading, page]. It is read once here, never once per page.
    # Entries pointing below page 1 are broken bookmarks, and
    # omb_circular_a136_2026.pdf has one. They are filtered out into a new
    # list. The PDF itself is never modified.
    outline = [(heading, page_num) for _, heading, page_num in doc.get_toc()
               if page_num >= 1]
    sections = _sections_by_page(outline, doc.page_count)

    # Read every page before cleaning any, because boilerplate can only be
    # spotted by comparing the pages against each other.
    raw = [pdf_page.get_text() for pdf_page in doc]
    junk = _boilerplate(raw)

    pages = []
    for index, text in enumerate(raw):
        number = index + 1  # pymupdf counts from 0, a reader counts from 1
        cleaned = tidy(_strip_boilerplate(text, junk))
        if len(cleaned) < MIN_PAGE_CHARS:
            continue
        pages.append(Page(
            source=path.name,
            title=title,
            url=url,
            page=number,
            section=sections[number],
            text=cleaned,
        ))

    return pages


def read_ecfr(path, parts=("210", "229")) -> list[Page]:
    """Read the eCFR XML, one record per section of the Parts we want.

    This file has no pages, so one record is one section and page stays None.

    It also holds every Part of Title 17, dozens of them, covering broker
    dealers and exchanges among other things. Only Part 210 (Regulation S-X)
    and Part 229 (Regulation S-K) say how financial statements must be
    presented. Loading the rest would bury every search under unrelated rules.
    """
    path = Path(path)
    title, url = CORPUS.get(path.name, (path.stem, ""))
    root = ET.parse(path).getroot()

    records = []
    for part in root.iter("DIV5"):          # DIV5 is a Part
        if part.get("N") not in parts:
            continue
        for section in part.iter("DIV8"):   # DIV8 is a section
            # The N attribute reads "§ 210.1-01". Drop the sign, keep the number.
            label = SECTION_SIGN.sub("", section.get("N", "")).strip()
            # itertext gathers this section's text and everything nested inside
            # it. Joining on a space stops the end of one tag running into the
            # start of the next; tidy collapses the extra spaces afterwards.
            text = tidy(" ".join(section.itertext()))
            if len(text) < MIN_PAGE_CHARS:
                continue
            records.append(Page(
                source=path.name,
                title=title,
                url=url,
                page=None,
                section=label or None,
                text=text,
            ))

    return records


def load_corpus(folder=CORPUS_DIR) -> list[Page]:
    """Read every document in the corpus folder into one list of Page records."""
    folder = Path(folder)
    records = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() == ".pdf":
            records += read_pdf(path)
        elif path.suffix.lower() == ".xml":
            records += read_ecfr(path)
    return records
