"""Tests for lineage/diff.py.

No workbook, no database, no model. Every Finding is built by hand, so the
whole file runs in milliseconds and in CI.
"""

from finlint.lineage.diff import RunDiff, RunRecord, diff_runs, finding_key, first_seen
from finlint.rules.model import Finding


def make_finding(rule_id, coordinate, blast_radius=0, sheet="Model",
                 severity="high", message="m"):
    """Build a Finding by hand so no test needs a workbook."""
    return Finding(rule_id=rule_id, sheet=sheet, coordinate=coordinate,
                   blast_radius=blast_radius, severity=severity, message=message)


# --- finding_key, the shared definition of "the same finding" --------------

def test_key_ignores_messages_and_severity():
    """Only the rule, sheet and cell identify a finding.

    If severity or the message were part of the key, a reworded message or a
    severity change would make an old problem look brand new.
    """
    f1 = make_finding("r1", "C15", blast_radius=4, severity="high", message="m1")
    f2 = make_finding("r1", "C15", blast_radius=7, severity="low", message="m2")

    assert finding_key(f1) == finding_key(f2)


def test_key_includes_the_rule():
    """Two different rules on the same cell are two different problems.

    If C15 held a hardcoded value in v1 and a circular reference in v3, that
    is not one problem that changed shape.
    """
    hardcode = make_finding("hardcoded_value", "C15")
    circular = make_finding("circular_reference", "C15")

    assert finding_key(hardcode) != finding_key(circular)


# --- diff_runs -------------------------------------------------------------

def test_identical_runs_are_still_there():
    """Nothing changed, so nothing is new and nothing was fixed."""
    f1 = make_finding("r1", "C15")
    f2 = make_finding("r2", "C16")

    result = diff_runs([f1, f2], [f1, f2])

    assert result.new == []
    assert result.resolved == []
    assert result.still_there == [f1, f2]


def test_a_finding_only_in_current_is_new():
    """A problem that was not there last time is new."""
    f1 = make_finding("r1", "C15")
    f2 = make_finding("r2", "C16")

    result = diff_runs([f1], [f1, f2])

    assert result.new == [f2]
    assert result.resolved == []


def test_a_finding_only_in_previous_is_resolved():
    """A problem that has gone was fixed, and must be reported as such.

    This is the test that catches reading from the wrong list. A resolved
    finding exists only in the previous run, so building the bucket from
    current leaves it empty for ever and nobody notices.
    """
    f1 = make_finding("r1", "C15")
    f2 = make_finding("r2", "C16")

    result = diff_runs([f1, f2], [f1])

    assert result.new == []
    assert result.resolved == [f2]


def test_same_cell_different_rule_counts_twice():
    """One cell, two rules, so one problem was fixed and another appeared."""
    hardcode = make_finding("hardcoded_value", "C15")
    circular = make_finding("circular_reference", "C15")

    result = diff_runs([hardcode], [circular])

    assert result.new == [circular]
    assert result.resolved == [hardcode]
    assert result.still_there == []


def test_blast_radius_change_is_the_same_finding():
    """A finding getting worse is still the same finding, with today's numbers.

    Two things are asserted. The key ignores blast_radius, so this counts as
    one finding. And still_there carries the object from the CURRENT run, so
    the reviewer sees 7 rather than the stale 4.
    """
    before = make_finding("hardcoded_value", "C15", blast_radius=4)
    after = make_finding("hardcoded_value", "C15", blast_radius=7)

    result = diff_runs([before], [after])

    assert len(result.still_there) == 1
    assert result.still_there[0].blast_radius == 7


def test_first_run_has_everything_new():
    """The very first upload of a file has no previous run to compare to."""
    f1 = make_finding("r1", "C15")
    f2 = make_finding("r2", "C16")

    result = diff_runs([], [f1, f2])

    assert result.new == [f1, f2]
    assert result.still_there == []
    assert result.resolved == []


def test_everything_fixed_leaves_nothing_current():
    """A workbook that came back clean reports every old finding as resolved."""
    f1 = make_finding("r1", "C15")

    result = diff_runs([f1], [])

    assert result.resolved == [f1]
    assert result.new == []


# --- first_seen ------------------------------------------------------------

def test_present_in_every_run_returns_one():
    """A finding in all three runs has been there since version 1.

    Catches the overwrite bug: if the loop kept going instead of returning on
    the first match, this would report 3.
    """
    f1 = make_finding("r1", "C15")
    history = [RunRecord(version=v, findings=[f1]) for v in (1, 2, 3)]

    assert first_seen(f1, history) == 1


def test_appearing_later_returns_that_version():
    """A finding that turns up in run 3 is reported as version 3."""
    old = make_finding("r1", "C15")
    recent = make_finding("r2", "C16")

    history = [
        RunRecord(version=1, findings=[old]),
        RunRecord(version=2, findings=[old]),
        RunRecord(version=3, findings=[old, recent]),
    ]

    assert first_seen(recent, history) == 3


def test_unknown_finding_returns_none():
    """A finding in no run at all has no first version."""
    f1 = make_finding("r1", "C15")
    stranger = make_finding("r2", "Z99")

    history = [RunRecord(version=1, findings=[f1]), RunRecord(version=2, findings=[f1])]

    assert first_seen(stranger, history) is None


def test_empty_history_returns_none():
    """Nothing to search, so there is no answer rather than a wrong one."""
    assert first_seen(make_finding("r1", "C15"), []) is None


def test_version_comes_from_the_record_not_the_position():
    """A gap in the version numbers must not shift the answer.

    With versions 1, 3 and 4 stored, the run at position 3 is version 4.
    Counting positions reported 3 here, so the badge read "since v3" for a
    finding that first appeared in v4. This is the test for that fix.
    """
    early = make_finding("r1", "C15")
    late = make_finding("r4", "Z9")

    history = [
        RunRecord(version=1, findings=[early]),
        RunRecord(version=3, findings=[early]),
        RunRecord(version=4, findings=[early, late]),
    ]

    assert first_seen(late, history) == 4
    assert first_seen(early, history) == 1


def test_records_out_of_order_still_give_the_earliest():
    """Earliest version wins even if the records arrive unsorted."""
    f1 = make_finding("r1", "C15")

    history = [
        RunRecord(version=3, findings=[f1]),
        RunRecord(version=1, findings=[f1]),
    ]

    assert first_seen(f1, history) == 1


def test_a_returning_finding_reports_its_first_version():
    """Present in v1, gone in v2, back in v3 is reported as v1.

    This pins down a deliberate simplification rather than a bug. Saying
    "returned in v3" would need continuous-run tracking, and for a reviewer
    "this has been seen before" is the useful answer either way. The test
    exists so nobody changes the behaviour by accident.
    """
    f1 = make_finding("r1", "C15")
    other = make_finding("r2", "C16")

    history = [
        RunRecord(version=1, findings=[f1]),
        RunRecord(version=2, findings=[other]),
        RunRecord(version=3, findings=[f1]),
    ]

    assert first_seen(f1, history) == 1
