"""Convert pattern matches into placer hints."""

from __future__ import annotations

from typing import Any

from wirewright.ir.model import Orientation, Schematic
from wirewright.ir.validate import LTSPICE_GRID
from wirewright.patterns.matcher import PatternMatch


def matches_to_pinned_hints(
    matches: list[PatternMatch], anchor_step: int = LTSPICE_GRID * 16
) -> dict[str, tuple[int, int, Orientation]]:
    """For each match, lay out its components at fixed positions in the canvas.

    The first match's anchor sits at ``(0, 0)``; subsequent matches step right
    by ``anchor_step`` so they don't collide. Each match's :class:`PlacementHint`
    list specifies role → ``(dx, dy, orientation)`` relative to the anchor.
    """
    pinned: dict[str, tuple[int, int, Orientation]] = {}
    for i, match in enumerate(matches):
        anchor_x = i * anchor_step
        anchor_y = 0
        for hint in match.placement:
            ref = match.role_to_ref.get(hint.role)
            if ref is None:
                continue
            pinned[ref] = (anchor_x + hint.dx, anchor_y + hint.dy, hint.orientation)
    return pinned


def build_hints_from_patterns(schematic: Schematic) -> dict[str, Any]:
    """One-shot helper for the CLI: find matches and return a hints dict."""
    from wirewright.patterns.matcher import find_matches

    matches = find_matches(schematic)
    return {"pinned": matches_to_pinned_hints(matches), "_matches": matches}
