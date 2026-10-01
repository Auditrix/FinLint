"""The shared shape of one problem found in one cell, agreed by Nara and Sowb.

Fields only, no logic. checks.py creates these, engine.py sorts them, and the
evaluation code counts them. Frozen: change it only when both of us agree.
"""

from typing import Literal

from pydantic import BaseModel

# The four severities a finding can carry, worst first.
Severity = Literal["critical", "high", "medium", "low"]

# The same four in order, for sorting findings. Index 0 is the worst.
SEVERITY_ORDER = ("critical", "high", "medium", "low")


class Finding(BaseModel):
    """One problem, in one cell, found by one check."""

    rule_id: str          # which check found it, e.g. "hardcoded_value"
    severity: Severity    # how serious it is, critical is the worst
    sheet: str            # the worksheet it sits on
    coordinate: str       # the cell address, e.g. "C15"
    message: str          # plain words a non technical reader can act on
    blast_radius: int = 0  # cells broken downstream; filled in after the check runs
