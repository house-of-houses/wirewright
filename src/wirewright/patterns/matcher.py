"""Subgraph isomorphism matcher for analog idiom recognition.

PHASE 5. Not implemented in v0.0.1.

Implementation plan: wrap NetworkX's ``isomorphism.GraphMatcher`` (VF2) to
search the IR graph for instances of registered pattern templates. Returns
a list of matches with role-to-component-ref mappings and placement
constraints to feed to the underlying placer.
"""

from __future__ import annotations

from dataclasses import dataclass

from wirewright.ir.model import Schematic


@dataclass(frozen=True)
class PatternMatch:
    """A successful match of one pattern instance in the schematic."""

    pattern_name: str
    pattern_version: str
    role_to_ref: dict[str, str]
    """Role names in the template to component refs in the schematic."""

    constraints: list[object]
    """Placement constraints to pass to the placer as hints."""


def find_matches(schematic: Schematic) -> list[PatternMatch]:
    """Find all pattern matches in the schematic.

    PHASE 5: not implemented.
    """
    raise NotImplementedError("Phase 5 deliverable. See docs/PLAN.md.")
