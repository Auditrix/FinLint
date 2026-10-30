"""Tests for db/store.py.

Every test here needs a live PostgreSQL, so they are skipped when none is
reachable, the same pattern test_retrieve.py uses for the database and
test_chunk.py uses for the tokenizer.

Each test creates its own file name and deletes its rows afterwards, so the
tests leave no trace and can run in any order.
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from finlint.db.store import (
    SCHEMA,
    approve,
    file_hash,
    load_approvals,
    load_history,
    save_run,
)
from finlint.lineage.diff import diff_runs, finding_key, first_seen
from finlint.pipeline import check_file
from finlint.rules.model import Finding

FIXTURE = "tests/fixtures/circular.xlsx"


def _database_available():
    """Whether a PostgreSQL with our tables is reachable right now."""
    try:
        from finlint.rag.store import connect
        conn = connect()
        with conn.cursor() as cur:
            for statement in SCHEMA:
                cur.execute(statement)
        conn.commit()
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(
    not _database_available(),
    reason="no reachable PostgreSQL",
)


@pytest.fixture
def conn():
    """A connection to the test database."""
    from finlint.rag.store import connect
    return connect()


@pytest.fixture
def temp_workbook(tmp_path, conn):
    """A real copy of the fixture, under a file name unique to this test.

    It has to be a real file on disk, because save_run hashes the bytes at
    result.path. Named from the clock so two runs of the suite never collide.

    Yields the full path. Tests that only need the stored name use
    Path(...).name, which is what save_run records.
    """
    name = f"zz_test_{datetime.now(timezone.utc).timestamp()}.xlsx"
    path = tmp_path / name
    shutil.copy(FIXTURE, path)

    yield str(path)

    # Deleted in reverse dependency order because of the foreign keys.
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM files WHERE name = %s", (name,))
        row = cur.fetchone()
        if row:
            file_id = row[0]
            cur.execute(
                "DELETE FROM findings WHERE run_id IN "
                "(SELECT id FROM runs WHERE file_id = %s)", (file_id,))
            cur.execute("DELETE FROM approvals WHERE file_id = %s", (file_id,))
            cur.execute("DELETE FROM runs WHERE file_id = %s", (file_id,))
            cur.execute("DELETE FROM files WHERE id = %s", (file_id,))
    conn.commit()


def make_finding(rule_id="r1", coordinate="A1", sheet="S", blast_radius=0):
    return Finding(rule_id=rule_id, severity="high", sheet=sheet,
                   coordinate=coordinate, message="m", blast_radius=blast_radius)


def _insert_run(conn, file_id, version, findings):
    """Insert one run with the findings given, so tests can build any history."""
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO runs(file_id,version,created_at,score,report,sha256) "
            "VALUES (%s,%s,%s,0,'','x') RETURNING id", (file_id, version, now))
        run_id = cur.fetchone()[0]
        for f in findings:
            cur.execute(
                "INSERT INTO findings(run_id,rule_id,severity,sheet,coordinate,"
                "message,blast_radius) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (run_id, f.rule_id, f.severity, f.sheet, f.coordinate,
                 f.message, f.blast_radius))
    conn.commit()
    return run_id


def _make_file(conn, name):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO files(name,first_seen_at) VALUES (%s,%s) RETURNING id",
                    (name, datetime.now(timezone.utc)))
        file_id = cur.fetchone()[0]
    conn.commit()
    return file_id


# --- file_hash, no database needed ----------------------------------------

def test_hash_is_stable():
    """The same file hashes the same twice, which is what detects no change."""
    assert file_hash(FIXTURE) == file_hash(FIXTURE)


def test_hash_differs_between_files():
    """Two different workbooks do not share a hash."""
    assert file_hash(FIXTURE) != file_hash("tests/fixtures/hardcode.xlsx")


# --- save_run -------------------------------------------------------------

@needs_db
def test_second_save_is_version_two(conn, temp_workbook):
    """Saving the same file twice gives versions 1 and 2, and ONE file row.

    The version counter is also the test that a file's first run does not
    crash: max(version) over no rows returns None, not an empty result, so
    None + 1 would raise.
    """
    name = Path(temp_workbook).name
    result = check_file(temp_workbook)

    save_run(conn, result)
    save_run(conn, result)

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM files WHERE name = %s", (name,))
        assert cur.fetchone()[0] == 1

        cur.execute("SELECT version FROM runs WHERE file_id = "
                    "(SELECT id FROM files WHERE name = %s) ORDER BY version",
                    (name,))
        assert [r[0] for r in cur.fetchall()] == [1, 2]


@needs_db
def test_findings_are_stored_with_the_run(conn, temp_workbook):
    """Every finding from the run is written, not just the run row."""
    result = check_file(temp_workbook)

    save_run(conn, result)
    history = load_history(conn, Path(temp_workbook).name)

    assert len(history) == 1
    assert history[0].version == 1
    assert len(history[0].findings) == len(result.findings)


# --- load_history ---------------------------------------------------------

@needs_db
def test_an_empty_run_still_gets_its_place(conn, temp_workbook):
    """Three runs where the middle one found nothing must return THREE lists.

    This is the bug that actually happened. A plain JOIN drops the empty run,
    and an elif in the grouping loop adds a second empty list. Either way the
    list length stops matching the stored version numbers, and first_seen
    counts positions, so every badge after the empty run is wrong.
    """
    file_id = _make_file(conn, Path(temp_workbook).name)
    _insert_run(conn, file_id, 1, [make_finding("r1")])
    _insert_run(conn, file_id, 2, [])            # found nothing
    _insert_run(conn, file_id, 3, [make_finding("r3")])

    history = load_history(conn, Path(temp_workbook).name)

    assert len(history) == 3
    assert [r.version for r in history] == [1, 2, 3]
    assert [len(r.findings) for r in history] == [1, 0, 1]


@needs_db
def test_history_is_oldest_first(conn, temp_workbook):
    """Oldest first, and each record carries its own stored version number."""
    file_id = _make_file(conn, Path(temp_workbook).name)
    _insert_run(conn, file_id, 1, [make_finding("oldest")])
    _insert_run(conn, file_id, 2, [make_finding("newest")])

    history = load_history(conn, Path(temp_workbook).name)

    assert history[0].version == 1
    assert history[0].findings[0].rule_id == "oldest"
    assert history[1].version == 2
    assert history[1].findings[0].rule_id == "newest"


@needs_db
def test_history_round_trips_through_diff_runs(conn, temp_workbook):
    """Two identical runs come back as nothing changed.

    This is the test that proves save_run, load_history and diff_runs all
    agree on what a finding is. If any column were dropped or renamed on the
    way through the database, findings would stop matching and this would
    report everything as new and resolved at once.
    """
    result = check_file(temp_workbook)
    save_run(conn, result)
    save_run(conn, result)

    history = load_history(conn, Path(temp_workbook).name)
    difference = diff_runs(history[0].findings, history[1].findings)

    assert difference.new == []
    assert difference.resolved == []
    assert len(difference.still_there) == len(result.findings)


@needs_db
def test_history_keeps_findings_worst_first(conn, temp_workbook):
    """save_run inserts them ranked, and the page promises worst first."""
    ranked = [make_finding(coordinate=f"A{n}") for n in range(1, 40)]
    file_id = _make_file(conn, Path(temp_workbook).name)
    _insert_run(conn, file_id, 1, ranked)

    stored = load_history(conn, Path(temp_workbook).name)[-1].findings

    assert [f.coordinate for f in stored] == [f.coordinate for f in ranked]


def test_unknown_file_has_no_history(conn):
    """A file never checked returns an empty list, not an error."""
    assert load_history(conn, "zz_never_seen.xlsx") == []


# --- approve and load_approvals -------------------------------------------

@needs_db
def test_an_approval_matches_its_finding_key(conn, temp_workbook):
    """load_approvals returns keys that finding_key produces, with no conversion.

    This is the only reason the set holds (rule_id, sheet, coordinate) in that
    order. Change either side and the UI stops greying out accepted findings,
    with no error anywhere.
    """
    file_id = _make_file(conn, Path(temp_workbook).name)
    finding = make_finding("hardcoded_value", "C15", sheet="Model")
    _insert_run(conn, file_id, 1, [finding])

    approve(conn, Path(temp_workbook).name, finding, "Deliberate, locked by policy", "nara")

    assert finding_key(finding) in load_approvals(conn, Path(temp_workbook).name)


@needs_db
def test_approving_twice_keeps_both_decisions(conn, temp_workbook):
    """The table keeps every decision, while the set collapses them to one.

    Deliberate: the audit trail needs who decided what and why, including a
    changed mind. The set is only answering "has this been accepted".
    """
    file_id = _make_file(conn, Path(temp_workbook).name)
    finding = make_finding("hardcoded_value", "C15")
    _insert_run(conn, file_id, 1, [finding])

    approve(conn, Path(temp_workbook).name, finding, "first reason", "nara")
    approve(conn, Path(temp_workbook).name, finding, "second reason", "sowb")

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM approvals WHERE file_id = %s", (file_id,))
        assert cur.fetchone()[0] == 2

    assert len(load_approvals(conn, Path(temp_workbook).name)) == 1


@needs_db
def test_approving_an_unknown_file_raises(conn):
    """You cannot accept a finding on a workbook that was never checked."""
    with pytest.raises(ValueError):
        approve(conn, "zz_never_seen.xlsx", make_finding(), "why", "nara")


@needs_db
def test_unknown_file_has_no_approvals(conn):
    """An empty set, not an error, so a first run renders fine."""
    assert load_approvals(conn, "zz_never_seen.xlsx") == set()


@needs_db
def test_a_finding_never_reported_cannot_be_approved(conn, temp_workbook):
    """You cannot silence a finding that was never raised.

    Without this guard a caller could approve every cell of a sheet, so every
    future finding there would be greyed out before it was ever reported,
    while the approvals table showed a trail of apparently genuine human
    decisions. That is a suppression path with no way to detect it.
    """
    file_id = _make_file(conn, Path(temp_workbook).name)
    _insert_run(conn, file_id, 1, [make_finding("hardcoded_value", "C15")])

    never_raised = make_finding("formula_drift", "Z99")

    with pytest.raises(ValueError):
        approve(conn, Path(temp_workbook).name, never_raised, "looks fine", "nara")


@needs_db
def test_an_approval_needs_a_reason(conn, temp_workbook):
    """A blank reason still hides the finding, so it must be rejected.

    The reason is the control. An approval with none would suppress a defect
    while recording nothing about why.
    """
    file_id = _make_file(conn, Path(temp_workbook).name)
    finding = make_finding("hardcoded_value", "C15")
    _insert_run(conn, file_id, 1, [finding])

    with pytest.raises(ValueError):
        approve(conn, Path(temp_workbook).name, finding, "   ", "nara")

    with pytest.raises(ValueError):
        approve(conn, Path(temp_workbook).name, finding, "a real reason", "")


@needs_db
def test_a_failed_save_leaves_nothing_behind(conn, tmp_path):
    """A save that fails part way must roll back completely.

    file_hash is read before the transaction opens, but this proves the whole
    write is atomic: a partial run used to stay pending and get committed by
    whatever the caller did next, leaving a run with no findings, which makes
    diff_runs report every earlier finding as resolved.
    """
    import shutil
    name = f"zz_rollback_{datetime.now(timezone.utc).timestamp()}.xlsx"
    path = tmp_path / name
    shutil.copy(FIXTURE, path)
    result = check_file(str(path))

    path.unlink()  # the file disappears before the save

    with pytest.raises(FileNotFoundError):
        save_run(conn, result)

    conn.commit()  # a caller carrying on with the same connection

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM files WHERE name = %s", (name,))
        assert cur.fetchone()[0] == 0


@needs_db
def test_a_version_gap_does_not_shift_the_reported_version(conn, temp_workbook):
    """A deleted run in the middle must not change what first_seen reports.

    save_run takes max(version)+1, so removing any run but the newest leaves
    a permanent hole. Reading the version from the list position used to
    report v3 for a finding first seen in v4, with nothing to show it.
    """
    name = Path(temp_workbook).name
    file_id = _make_file(conn, name)
    early = make_finding("r1", "C15")
    late = make_finding("r4", "Z9")

    _insert_run(conn, file_id, 1, [early])
    _insert_run(conn, file_id, 3, [early])          # version 2 is missing
    _insert_run(conn, file_id, 4, [early, late])

    history = load_history(conn, name)

    assert [r.version for r in history] == [1, 3, 4]
    assert first_seen(late, history) == 4
    assert first_seen(early, history) == 1


@needs_db
def test_a_save_after_a_read_survives_the_connection_closing(temp_workbook):
    """A read before a save must not make the save vanish.

    Any plain SELECT leaves a psycopg 3 connection inside a transaction. A save
    wrapped in conn.transaction() on that connection only becomes a savepoint,
    and it was discarded when the connection closed: verified to lose every run.
    An API handler that reads, then saves, is exactly this sequence.
    """
    from finlint.rag.store import connect

    name = Path(temp_workbook).name
    result = check_file(temp_workbook)

    first = connect()
    load_history(first, name)          # a read, as an API handler would do
    save_run(first, result)
    first.close()                      # the handler ends without committing

    second = connect()
    assert len(load_history(second, name)) == 1
    second.close()
