"""Tests for retrieve.py.

The id and question logic needs no database, so those tests run in CI. The
two that do need one are skipped when no database is reachable, the same way
test_chunk.py skips when the tokenizer cannot be loaded.
"""

import pytest

from finlint.rag.retrieve import QUESTIONS, Hit, _neighbor_ids, question_for
from finlint.rules.checks import ALL_CHECKS
from finlint.rules.model import Finding

# A real chunk_id. The file name contains underscores, which is exactly why
# the id has to be split on its last colon and not on an underscore.
REAL_ID = "gao_green_book_2025.pdf:13:2"


def _database_available():
    """Whether a Postgres with our table is reachable right now.

    The container is not running in CI and may not be running locally, so
    those tests are skipped rather than failed.
    """
    try:
        from finlint.rag.store import connect
        conn = connect()
        conn.execute("SELECT 1 FROM chunks LIMIT 1")
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(
    not _database_available(),
    reason="no database with a loaded chunks table",
)


def make_finding(rule_id="dead_input"):
    """A Finding to retrieve against, built by hand."""
    return Finding(
        rule_id=rule_id,
        severity="low",
        sheet="Model",
        coordinate="C15",
        message="typed value that no formula reads",
    )


# --- the id logic ----------------------------------------------------------

def test_ids_split_on_the_last_colon():
    """The id is split on its final colon, never on an underscore.

    "gao_green_book_2025.pdf:13:2" split on an underscore gives
    "2025.pdf:13:2" as the index, which crashes on int(). The file name owns
    the underscores, the id structure owns the colons.
    """
    assert _neighbor_ids(REAL_ID) == [
        "gao_green_book_2025.pdf:13:1",
        "gao_green_book_2025.pdf:13:3",
    ]


def test_the_chunk_itself_is_not_a_neighbour():
    """Only the pieces either side, never index 2 itself.

    Hit.chunk already holds it. Including it again would put that passage
    twice in the joined text, so a quote could appear to match across the
    duplicated seam when it does not exist there.
    """
    assert REAL_ID not in _neighbor_ids(REAL_ID)


def test_first_chunk_has_no_negative_neighbour():
    """At index 0 there is nothing before, so only the one after is asked for."""
    assert _neighbor_ids("doc.pdf:13:0") == ["doc.pdf:13:1"]


def test_ecfr_id_still_splits_correctly():
    """An eCFR id uses a section number, which itself contains dots and dashes.

    Those records have no page number, so the locator is the section. The
    split still only cares about the last colon.
    """
    assert _neighbor_ids("ecfr_title17.xml:210.14-01-02:1") == [
        "ecfr_title17.xml:210.14-01-02:0",
        "ecfr_title17.xml:210.14-01-02:2",
    ]


# --- the question mapping --------------------------------------------------

def test_question_is_about_the_concept_not_the_cell():
    """A mapped rule returns its fixed question, not the finding's message.

    Searching the corpus for "C15" finds nothing: federal accounting
    standards do not mention anybody's spreadsheet.
    """
    question = question_for(make_finding("dead_input"))

    assert question == QUESTIONS["dead_input"]
    assert "C15" not in question


def test_unknown_rule_falls_back_to_the_message():
    """A check added before its question still searches for something."""
    finding = make_finding("a_rule_invented_tomorrow")

    assert question_for(finding) == finding.message


def test_every_check_has_a_question():
    """One question per check, so adding a seventh check fails this test.

    Without it, a new rule would silently fall back to its own message, which
    searches the accounting corpus using spreadsheet wording and retrieves
    nothing useful.
    """
    assert len(QUESTIONS) == len(ALL_CHECKS)


def test_the_six_known_rules_are_mapped():
    """The rule_ids that rules/checks.py actually emits are all present."""
    assert set(QUESTIONS) == {
        "error_cells",
        "circular_reference",
        "dead_input",
        "hardcoded_value",
        "broken_link",
        "formula_drift",
    }


# --- against a real database -----------------------------------------------

@needs_db
def test_retrieve_returns_ranked_hits():
    """A Finding goes in, cited passages come out, best first."""
    from finlint.rag.retrieve import retrieve
    from finlint.rag.store import connect

    hits = retrieve(connect(), make_finding(), limit=3)

    assert len(hits) == 3
    assert all(isinstance(h, Hit) for h in hits)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    assert all(0 <= h.score <= 1 for h in hits)


@needs_db
def test_every_hit_can_be_cited():
    """A finding a human cannot verify is worthless, so title and url must be set."""
    from finlint.rag.retrieve import retrieve
    from finlint.rag.store import connect

    hits = retrieve(connect(), make_finding(), limit=3)

    assert all(h.chunk.title for h in hits)
    assert all(h.chunk.url.startswith("http") for h in hits)


@needs_db
def test_neighbours_sit_either_side_of_the_hit():
    """Each neighbour's index is exactly one away from the hit's."""
    from finlint.rag.retrieve import retrieve
    from finlint.rag.store import connect

    for hit in retrieve(connect(), make_finding(), limit=3):
        for neighbour in hit.neighbors:
            assert abs(neighbour.chunk_index - hit.chunk.chunk_index) == 1
            assert neighbour.source == hit.chunk.source
