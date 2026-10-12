"""Tests for chunk.py.

Most of these pass max_tokens=None, which skips the token check, so they test
the character logic without loading a tokenizer. The three at the bottom do
load it, because the token limit is the whole reason this module exists.

No test here reads a file. A Page is built by hand, so everything runs in CI.
"""

from finlint.rag.chunk import (
    MAX_TOKENS,
    Chunk,
    _fit_token_limit,
    _token_count,
    chunk_page,
    chunk_pages,
    split_text,
)
from finlint.rag.corpus import Page

# The overlap split_text uses by default. Named here so the tests that check
# overlapping read clearly instead of repeating a bare 200.
OVERLAP = 200


def make_page(text, page=1, section="Intro"):
    """Build a Page by hand, so no test needs a real document on disk."""
    return Page(
        source="test.pdf",
        title="Test Document",
        url="https://example.gov/test.pdf",
        page=page,
        section=section,
        text=text,
    )


# --- split_text, the character logic ---------------------------------------

def test_does_not_hang():
    """A single blank line early, and none after it, must still terminate.

    This was a real bug. The piece ended at the blank line, the next start
    stepped back by the overlap, that same blank line was still the last one
    in the new window, so the same cut was chosen forever. Loading the corpus
    died with MemoryError. The guard is that a cut must leave end past
    start + overlap, not merely past start.
    """
    assert len(split_text("A" * 1000 + "\n\n" + "B" * 4000)) > 1


def test_short_text_is_one_piece():
    """Text under the target is returned whole, untouched."""
    assert split_text("short page") == ["short page"]


def test_nothing_is_lost():
    """The pieces rebuild the original exactly.

    Each piece after the first starts with OVERLAP characters copied from the
    one before it, so those are dropped when rebuilding. Anything other than
    an exact match means text was dropped or duplicated.
    """
    original = "x" * 3000
    pieces = split_text(original)
    rebuilt = pieces[0] + "".join(p[OVERLAP:] for p in pieces[1:])

    assert rebuilt == original


def test_pieces_overlap():
    """Each piece repeats the tail of the previous one.

    This is what stops a sentence landing on a boundary from being cut in
    half in both pieces and found in neither.
    """
    pieces = split_text("x" * 3000)

    assert pieces[1][:OVERLAP] == pieces[0][-OVERLAP:]


def test_tiny_tail_is_merged():
    """A final piece carrying almost no new text is folded into the one before.

    2,210 characters would otherwise end with a 210 character piece holding
    just 10 characters of new text. Stored alone that is noise competing in
    every search. Note the merged piece is longer than the target, which is
    expected and still well inside the token limit.
    """
    pieces = split_text("x" * 2210)

    assert len(pieces) == 2
    assert [len(p) for p in pieces] == [1200, 1210]


def test_cuts_at_a_blank_line():
    """A paragraph break is preferred over cutting mid sentence."""
    text = "A" * 900 + "\n\n" + "B" * 900 + "\n\n" + "C" * 900
    pieces = split_text(text)

    # The first cut lands on the blank line at 900, so the piece is the A run.
    assert pieces[0] == "A" * 900


def test_sentence_keeps_its_period():
    """Cutting at a sentence end keeps the period with its sentence.

    The cut position is the period itself, so stopping there would drop it.
    This text has no blank lines, which forces the sentence branch.
    """
    pieces = split_text("Auditors must be independent. " * 60)

    assert pieces[0].endswith(".")


# --- chunk_page, carrying the fields across --------------------------------

def test_fields_are_copied():
    """The five document fields come across from the Page unchanged."""
    page = make_page("text that stays short")
    chunk = chunk_page(page, max_tokens=None)[0]

    assert chunk.source == "test.pdf"
    assert chunk.title == "Test Document"
    assert chunk.url == "https://example.gov/test.pdf"
    assert chunk.page == 1
    assert chunk.section == "Intro"


def test_text_is_the_piece_not_the_page():
    """A chunk holds its own slice, never a copy of the whole page.

    Nesting the page instead would have cost about 23 MB for the largest
    eCFR section alone, which becomes roughly 200 chunks.
    """
    page = make_page("y" * 3000)
    chunks = chunk_page(page, max_tokens=None)

    assert chunks[0].text != page.text
    assert chunks[0].text in page.text


def test_chunk_index_counts_from_zero():
    """Indices run 0, 1, 2 with no gaps, which is how neighbours are found."""
    chunks = chunk_page(make_page("y" * 3000), max_tokens=None)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_ids_are_unique_within_a_page():
    """No two chunks of one page share an id."""
    chunks = chunk_page(make_page("y" * 5000), max_tokens=None)

    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_ids_are_unique_across_pages():
    """Two pages of the same document never collide.

    The id uses the page number, not the heading. Keying on the heading gave
    133 duplicate ids in the Yellow Book alone, because its Glossary heading
    covers 11 pages, and the database would have kept one chunk of each set.
    """
    pages = [make_page("y" * 3000, page=n, section="Glossary") for n in (1, 2, 3)]
    chunks = chunk_pages(pages, max_tokens=None)

    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_ecfr_page_is_none_still_gets_an_id():
    """A record with no page number uses its section instead.

    All 236 eCFR records have page None. Without this they would all be
    keyed on the word None and overwrite each other.
    """
    page = make_page("short text", page=None, section="210.1-01")
    chunk = chunk_page(page, max_tokens=None)[0]

    assert "210.1-01" in chunk.chunk_id
    assert "None" not in chunk.chunk_id


def test_short_page_gives_one_chunk():
    """A page smaller than the target is not split at all."""
    chunks = chunk_page(make_page("one short page of text"), max_tokens=None)

    assert len(chunks) == 1
    assert chunks[0].text == "one short page of text"
    assert chunks[0].chunk_index == 0


# --- the token limit, the reason this module exists ------------------------

def test_text_within_the_limit_is_untouched():
    """A piece that already fits is returned as it is, not split."""
    assert _fit_token_limit("a short sentence") == ["a short sentence"]


def test_oversized_text_is_split_until_it_fits():
    """Text over 512 tokens is halved until every part fits.

    Counting characters can never guarantee a token count. Prose runs about
    4.4 characters per token, but account codes and citation strings run near
    1.7, so a 1,398 character chunk measured 844 tokens. This is the stage
    that catches those.
    """
    parts = _fit_token_limit("word " * 2000)

    assert len(parts) > 1
    assert all(_token_count(p) <= MAX_TOKENS for p in parts)


def test_no_chunk_from_a_page_exceeds_the_limit():
    """The guarantee, end to end: every chunk chunk_page emits fits the model.

    Dense text is used deliberately, since that is what broke the character
    based approach.
    """
    dense = "1010.5600 2990.1400 § 210.14-01-02 " * 400
    chunks = chunk_page(make_page(dense))

    assert all(_token_count(c.text) <= MAX_TOKENS for c in chunks)
