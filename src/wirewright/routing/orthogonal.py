"""Axis-aligned wire routing primitives.

Pure helpers shared by every placer. No placement logic; the placer decides
where pins are, this module decides how to draw the wire between them.
"""

from __future__ import annotations

from wirewright.ir.model import Wire
from wirewright.ir.validate import LTSPICE_GRID


def snap_to_grid(point: tuple[int, int]) -> tuple[int, int]:
    """Round an (x, y) to the nearest LTspice grid point."""
    return (
        round(point[0] / LTSPICE_GRID) * LTSPICE_GRID,
        round(point[1] / LTSPICE_GRID) * LTSPICE_GRID,
    )


def l_shape(a: tuple[int, int], b: tuple[int, int]) -> list[Wire]:
    """Two axis-aligned wire segments connecting ``a`` to ``b`` through an L bend.

    Snaps endpoints to the LTspice grid. The bend is horizontal-first.
    Returns a single-segment list when ``a`` and ``b`` are colinear on x or y.
    """
    ax, ay = snap_to_grid(a)
    bx, by = snap_to_grid(b)
    if ax == bx or ay == by:
        return [Wire(ax, ay, bx, by)]
    return [
        Wire(ax, ay, bx, ay),
        Wire(bx, ay, bx, by),
    ]


def manhattan_segments(points: list[tuple[int, int]]) -> list[Wire]:
    """Connect a sequence of points pairwise with axis-aligned wires.

    Each consecutive pair is rendered as :func:`l_shape`. Useful for any
    edge given as a list of bend points.
    """
    wires: list[Wire] = []
    for i in range(len(points) - 1):
        wires.extend(l_shape(points[i], points[i + 1]))
    return wires
