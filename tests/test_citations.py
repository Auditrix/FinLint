"""Tests for the citation guardrail.

This is guardrail 1 from CLAUDE.md Section 9.1: the agent quotes a rule, and
we search the real corpus for that quote. If it is not there, the finding is
dropped before any human sees it.

Every Hit here is built by hand, so no test needs a database or a model.
"""

from finlint.guardrails.citations import MIN_QUOTE_CHARS, _searchable, verify_quote
from finlint.rag.chunk import Chunk
from finlint.rag.retrieve import Hit

# Three consecutive pieces of one page, written so a sentence runs from the
# end of piece 1 into piece 2. That is the case the neighbour join exists for.
PIECE_0 = "Overview of the standards and how they are organised for the reader."
PIECE_1 = "Internal control is a process effected by an entity's oversight body,"
PIECE_2 = "management, and other personnel, designed to provide assurance."


def make_chunk(index, text, page=90):
    """One Chunk, built by hand so no document or database is needed."""
    return Chunk(
        source="gao_green_book_2025.pdf",
        title="GAO Green Book 2025 (Internal Control Standards)",
        url="https://www.gao.gov/assets/gao-25-107721.pdf",
        page=page,
        section="Definition of Internal Control",
        text=text,
        chunk_index=index,
        chunk_id=f"gao_green_book_2025.pdf:{page}:{index}",
    )


def make_hit(hit_index=1):
    """A Hit on one piece, with the pieces either side as its neighbours.

    Note the neighbours do NOT contain the hit's own chunk, which matches what
    retrieve.py returns.
    """
    pieces = {0: PIECE_0, 1: PIECE_1, 2: PIECE_2}
    return Hit(
        chunk=make_chunk(hit_index, pieces[hit_index]),
        score=0.74,
        neighbors=[make_chunk(i, t) for i, t in pieces.items() if i != hit_index],
    )


# --- _searchable, the normalising helper ------------------------------------

def test_newlines_become_spaces():
    """Corpus text carries the PDF's line breaks, a typed quote does not.

    A real chunk looks like "Overview \\n \\n \\n \\nOV1.01 Internal control is",
    so an exact match against one flowing sentence would fail on text that is
    genuinely identical.
    """
    assert _searchable("Overview \n \n \nOV1.01 Internal") == "overview ov1.01 internal"


def test_curly_quotes_become_straight():
    """The PDFs use the typographic apostrophe, a person types the plain one."""
    assert _searchable("entity’s body") == _searchable("entity's body")


def test_case_is_ignored():
    """The model may capitalise differently when it quotes."""
    assert _searchable("Internal Control") == _searchable("internal control")


# --- verify_quote, the guardrail itself ------------------------------------

def test_a_real_quote_passes():
    """A passage copied out of the chunk is accepted."""
    assert verify_quote(PIECE_1, make_hit()) is True


def test_a_real_quote_reformatted_still_passes():
    """The same passage with curly quotes and line breaks is still accepted.

    If this failed, the guardrail would be throwing away correct citations,
    which is the opposite of its job.
    """
    messy = PIECE_1.replace("'", "’").replace(" ", "\n   ", 4).upper()

    assert verify_quote(messy, make_hit()) is True


def test_an_invented_quote_is_rejected():
    """A sentence that reads like government accounting but is not in the text.

    This is the test that matters. If a plausible sounding invention passes,
    the guardrail is not working and the system can cite rules that do not
    exist.
    """
    invented = "Management shall document all assumptions in a control register before approval."

    assert verify_quote(invented, make_hit()) is False


def test_a_quote_spanning_two_pieces_passes():
    """A quote running from one piece into the next is found.

    This only works because the pieces are joined in chunk_index order. The
    hit is piece 1, its neighbours are 0 and 2, and joining the chunk first
    would give the order 1, 0, 2, so this sentence would never be found.
    """
    spanning = PIECE_1 + " " + PIECE_2

    assert verify_quote(spanning, make_hit(hit_index=1)) is True


def test_a_quote_spanning_backwards_passes():
    """Same again, but the quote starts in the piece BEFORE the hit.

    Here the hit is piece 2, so the earlier piece has to be placed in front
    of it. This is the direction that a naive join gets wrong.
    """
    spanning = PIECE_1 + " " + PIECE_2

    assert verify_quote(spanning, make_hit(hit_index=2)) is True


def test_a_short_quote_is_rejected_even_when_real():
    """A few words prove nothing, because common phrases are on many pages.

    "internal control" appears throughout the corpus, so finding it is not
    evidence that the agent read the right passage.
    """
    short = "Internal control"

    assert len(short) < MIN_QUOTE_CHARS
    assert short in PIECE_1                      # it really is in the text
    assert verify_quote(short, make_hit()) is False   # and still rejected


def test_text_from_a_different_page_is_rejected():
    """A real corpus sentence that is not in THIS hit does not verify it.

    The agent has to quote the passage it actually retrieved, not something
    true from elsewhere in the document.
    """
    elsewhere = "Fraud risk factors include incentives, opportunities and attitudes."

    assert verify_quote(elsewhere, make_hit()) is False
