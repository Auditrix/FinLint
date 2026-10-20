"""Turn a list of findings into one number between 0 and 100.

This is for the third reader in CLAUDE.md Section 3, the finance director who
signs off and never opens the tool. They want to know whether a file is fine,
not which cell is wrong.

THE RULE THAT GOVERNS THIS FILE: the same findings must always give the same
score. No model, no randomness, no clock, and the input list is never altered.
An audit tool that reports 72 on Monday and 64 on Tuesday for an unchanged
file is worthless, which is why this is plain code and not an LLM call. See
CLAUDE.md Section 7, "the score is computed, not generated".
"""

from finlint.rules.model import SEVERITY_ORDER, Finding

# Base score for the worst severity found in the workbook. These are bands,
# not amounts to add up. A single critical finding has to land in the red band
# however few of them there are, and fifty harmless notes have to stay low.
WEIGHTS = {"critical": 80, "high": 60, "medium": 40, "low": 20}

# The most the blast radius can add on top of the base. Deliberately small:
# severity decides which band you are in, and damage only decides where you
# sit inside that band. Letting damage grow without a cap made one low
# warning touching ten cells score 100, higher than a real critical finding.
BLAST_BONUS = 20

# A blast radius at or above this earns the whole bonus. Taken from the seed
# models, where a genuinely serious finding breaks tens of cells downstream.
# Anything past it is already as bad as this score can express.
BLAST_FULL = 50


def risk_score(findings: list[Finding]) -> int:
    """Score one workbook from 0 (nothing found) to 100 (as bad as it gets).

    The worst severity present sets the band, then the largest blast radius
    at that severity decides the position inside it.

    The NUMBER of findings deliberately does not raise the score. A score that
    adds up per finding saturates immediately: Financial_Models.xlsx produces
    1,485 findings and FISY-ESSENTIEL produces 157, so both would read 100 and
    the number would no longer tell any two files apart.
    """
    if not findings:
        return 0

    # The worst severity present. Index 0 of SEVERITY_ORDER is the worst, so
    # the smallest index wins. Worked out from the data rather than trusting
    # the caller to have sorted it, and without sorting their list in place.
    worst = SEVERITY_ORDER[min(SEVERITY_ORDER.index(f.severity) for f in findings)]
    base = WEIGHTS[worst]

    # Only findings at that worst severity count towards the bonus. A low
    # warning with a huge blast radius must not inflate a file whose real
    # problem is a single critical cell.
    damage = max(f.blast_radius for f in findings if f.severity == worst)
    bonus = round(BLAST_BONUS * min(damage, BLAST_FULL) / BLAST_FULL)

    # The cap cannot bite with the weights above, since 80 + 20 is exactly
    # 100. It is here so that changing a weight can never produce 110.
    return min(100, base + bonus)
    