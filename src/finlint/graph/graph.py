"""The shared shape of the dependency map, agreed by Nara and Sowb.

Every node is a string in the agreed reference format, e.g. "BFR!B12".
Ranges of up to MAX_RANGE_CELLS cells are expanded into single cell nodes.
Whole columns and rows, like "BFR!A:A", stay as one node.

Fields only, no logic. build.py fills it, analyse.py reads it.
Frozen: change it only when both of us agree.
"""

from pydantic import BaseModel, Field

# Ranges larger than this stay as a single node, so a huge range never explodes the map.
MAX_RANGE_CELLS = 5000


class Graph(BaseModel):
    """What feeds what, stored in both directions so either question is one lookup."""

    feeds: dict[str, set[str]] = Field(default_factory=dict)       # cell -> the cells it reads
    feeds_into: dict[str, set[str]] = Field(default_factory=dict)  # cell -> the cells that read it
