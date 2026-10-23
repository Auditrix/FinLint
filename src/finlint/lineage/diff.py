"""Compare two runs of the same workbook, so a reviewer knows what changed.

This answers the one question that makes a second run worth reading: is this a
new problem, or has it been sitting in the file since version 1 and somebody
already looked at it? Without it every run shows the same forty findings and
nobody can tell what moved.

This is step 6 of the architecture in CLAUDE.md Section 7, and it is
deliberately plain code rather than an agent. Reading version history is set
comparison, so wrapping a model around it would risk a hallucinated version
number for no gain at all.

Every function here takes plain lists of Finding, never database rows. That
keeps the whole file testable with no database, and db/ simply supplies the
lists later. Same reason risk_score takes findings instead of a run record.

KNOWN LIMITATION: if somebody inserts a row, every coordinate below it shifts,
so every finding below the insert looks new. Tracking row shifts across
versions is a much harder problem and is out of scope here.
"""

from pydantic import BaseModel, Field

from finlint.rules.model import Finding


class RunDiff(BaseModel):
    """What changed between two runs of one workbook."""

    new: list[Finding] = Field(default_factory=list)          # in current, not in previous
    still_there: list[Finding] = Field(default_factory=list)  # in both runs
    resolved: list[Finding] = Field(default_factory=list)     # was in previous, now gone


def finding_key(finding: Finding) -> tuple[str, str, str]:
    """What makes two findings the same finding across two different runs.

    The rule, the sheet and the cell. All three are needed: if C15 held a
    hardcoded value in v1 and a circular reference in v3, those are two
    different problems on one cell, not one problem that changed.

    message and blast_radius are deliberately NOT part of the key. Both can
    change between runs while the problem stays the same, and a blast radius
    growing from 4 to 7 is the same finding getting worse, not a new one.

    Defined once here so every comparison in this file agrees on it.
    """
    return (finding.rule_id, finding.sheet, finding.coordinate)


def diff_runs(previous: list[Finding], current: list[Finding]) -> RunDiff:
    """Sort the current run's findings into new, still there, and resolved.

    resolved is the one that makes a dashboard worth looking at: it is how a
    reviewer sees that somebody fixed something, which is the whole point of
    the signer persona in CLAUDE.md Section 3.
    """
    prev_set = {finding_key(f) for f in previous}
    curr_set = {finding_key(f) for f in current}

    new = []
    still_there = []
    resolved = []

    # Both of these buckets take the object from current, not from previous,
    # so a still-there finding carries today's blast radius and message rather
    # than stale values from the older run.
    for item in current:
        if finding_key(item) not in prev_set:
            new.append(item)
        else:
            still_there.append(item)

    # Resolved findings have to come from previous. They do not exist in the
    # current run at all, so there is nothing in current to put here. Reading
    # from the wrong list leaves this list silently empty for ever.
    for item in previous:
        if finding_key(item) not in curr_set:
            resolved.append(item)

    return RunDiff(new=new, still_there=still_there, resolved=resolved)


def first_seen(finding: Finding, history: list[list[Finding]]) -> int | None:
    """Which version a finding first appeared in, counting from 1.

    history is every run of this workbook, oldest first, each one a plain list
    of findings. The CURRENT run must be included, or every finding comes back
    as None. The caller then compares: equal to the current version means
    "new", anything lower means "pre-existing since v{n}".

    Returns None when the finding is in no run at all.

    Simplification worth knowing: a finding present in v1, gone in v2 and back
    in v3 is reported as v1. Arguably it returned in v3, but saying so needs
    continuous-run tracking, and "it has been seen before" is the useful
    answer for a reviewer either way.
    """
    # Computed once rather than rebuilt on every run in the loop.
    key = finding_key(finding)

    # start=1 because people say "v1", while a Python list starts at 0. An
    # off-by-one here reaches the screen and looks like a bug in the feature.
    for version, run in enumerate(history, start=1):
        if key in {finding_key(f) for f in run}:
            return version  # the first match wins, so later runs never override it

    return None
