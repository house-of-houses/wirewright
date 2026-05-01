"""LTspice .asy symbol file parser.

PHASE 1. Not implemented in v0.0.1.

The plan: parse `.asy` files to extract pin offsets at runtime, replacing
the hand-curated table in ``wirewright.symbols.builtin``.
"""

from __future__ import annotations

from pathlib import Path

from wirewright.symbols.builtin import SymbolGeometry


def parse_asy_file(path: str | Path) -> SymbolGeometry:
    """Parse an LTspice ``.asy`` file and return its symbol geometry.

    PHASE 1: not implemented.
    """
    raise NotImplementedError("Phase 1 deliverable. See docs/PLAN.md.")
