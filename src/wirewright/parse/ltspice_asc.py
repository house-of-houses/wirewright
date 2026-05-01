"""LTspice .asc file parser. Used for round-trip tests against existing fixtures.

PHASE 1. Not implemented in v0.0.1.
"""

from __future__ import annotations

from pathlib import Path

from wirewright.ir.model import Schematic


def parse_asc_file(path: str | Path) -> Schematic:
    """Parse a `.asc` file into IR with positions populated.

    PHASE 1: not implemented. Phase 1 needs this to support round-trip tests
    where we parse a hand-drawn `.asc`, emit it back, and assert structural
    equivalence with the original.
    """
    raise NotImplementedError("Phase 1 deliverable. See docs/PLAN.md.")
