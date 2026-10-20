"""Tests for corpus.py.

Most of these touch no files at all, so they run in CI. data/ is gitignored,
so the two tests that need a real document are skipped when it is absent.
"""

import pytest
from pathlib import Path

from finlint.rag.corpus import (
    _boilerplate,
    _sections_by_page,
    _strip_boilerplate,
    read_ecfr,
    read_pdf,
    tidy,
)

CORPUS = Path("data/rag_corpus")
needs_data = pytest.mark.skipif(not CORPUS.exists(), reason="corpus not downloaded")


def test_tidy_normalis_quotes():
    """A curly apostrophe becomes a straight one.

    Without this, a quote typed by hand never matches the document text and
    the citation guardrail throws away a correct finding.
    """
    assert tidy("auditor’s") == "auditor's"


def test_tidy_collapses_spaces():
    """Runs of spaces become one, so spacing from the PDF layout is ignored."""
    assert tidy("a   b") == "a b"


def test_tidy_removes_nul_from_pdf_text():
    assert tidy("audit\x00 evidence") == "audit evidence"


def test_sections_carry_forward():
    """A page with no heading of its own belongs to the last heading before it.

    The returned list is indexed by page number, so index 1 is page 1. Intro
    starts on page 1 and Methods on page 10, so pages 1 to 9 are Intro and
    pages 10 to 12 are Methods.
    """
    result = _sections_by_page([("Intro", 1), ("Methods", 10)], 12)

    assert len(result) == 13          # 12 pages plus the unused slot 0
    assert result[1] == "Intro"
    assert result[9] == "Intro"       # carried forward, no heading of its own
    assert result[10] == "Methods"
    assert result[12] == "Methods"


def test_page_before_first_heading_is_none():
    """Pages before the document's first heading have no section.

    Three documents in the corpus have no heading until page 2, 5 or 7, so
    None is normal here and not an error.
    """
    result = _sections_by_page([("Intro", 3), ("Methods", 10)], 12)

    assert result[1] is None
    assert result[2] is None
    assert result[3] == "Intro"


def test_index_zero_is_unused():
    """Slot 0 is never filled, so sections[32] means page 32 and not page 33."""
    result = _sections_by_page([("Intro", 1)], 5)

    assert result[0] is None


def test_boilerplate_needs_most_pages():
    """A line on most pages is a footer. A line on one page is content."""
    pages = ["footer\nreal one", "footer\nreal two", "footer\nreal three"]
    junk = _boilerplate(pages)

    assert "footer" in junk
    assert "real one" not in junk


def test_boilerplate_ignores_a_tiny_document():
    """A two page document cannot call its only line boilerplate.

    The cutoff has a floor of 3, or every line of a short document would be
    stripped and nothing would be left to search.
    """
    assert _boilerplate(["only line", "only line"]) == set()


def test_page_label_is_stripped():
    """A line that is only a page label is dropped, the real text stays."""
    cleaned = _strip_boilerplate("Page 32\nreal text", set())

    assert "Page 32" not in cleaned
    assert "real text" in cleaned


def test_sentence_mentioning_a_page_is_kept():
    """A sentence that merely mentions a page is content, not a footer.

    This is why the regex is anchored with ^ and $. Without them, any
    sentence containing the word Page would be deleted.
    """
    cleaned = _strip_boilerplate("See Page 32 for details", set())

    assert cleaned == "See Page 32 for details"


@needs_data
def test_reads_a_real_pdf():
    """Every page of a real document becomes one record with a usable citation.

    This file is chosen on purpose: its outline holds a broken bookmark
    pointing at page -1, so it exercises the filter that drops those.
    """
    pages = read_pdf(CORPUS / "omb_circular_a136_2026.pdf")

    assert len(pages) == 124
    assert [p.page for p in pages] == list(range(1, 125))
    assert all(p.url for p in pages)
    assert all(p.title == "OMB Circular A-136 (2026)" for p in pages)


@needs_data
def test_ecfr_only_loads_two_parts():
    """Only Regulation S-X and S-K are loaded, and they carry no page number.

    Title 17 holds dozens of other Parts covering broker dealers and
    exchanges. Loading them would bury every search under unrelated rules.
    """
    records = read_ecfr(CORPUS / "ecfr_title17.xml")

    assert len(records) == 236
    assert all(r.page is None for r in records)
    assert all(r.section.startswith(("210.", "229.")) for r in records)
