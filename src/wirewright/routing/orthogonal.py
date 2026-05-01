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


def _segment_crossings(
    seg: tuple[tuple[int, int], tuple[int, int]],
    obstacles: list[tuple[int, int, int, int]],
) -> int:
    """Count obstacles whose interior the axis-aligned segment crosses.

    Touching an obstacle edge does not count as crossing.
    """
    (x1, y1), (x2, y2) = seg
    crossings = 0
    for x_min, y_min, x_max, y_max in obstacles:
        if x1 == x2:
            if x_min < x1 < x_max:
                lo, hi = min(y1, y2), max(y1, y2)
                if lo < y_max and hi > y_min:
                    crossings += 1
        else:
            if y_min < y1 < y_max:
                lo, hi = min(x1, x2), max(x1, x2)
                if lo < x_max and hi > x_min:
                    crossings += 1
    return crossings


def l_shape_avoiding(
    a: tuple[int, int],
    b: tuple[int, int],
    obstacles: list[tuple[int, int, int, int]],
) -> list[Wire]:
    """L-shape from ``a`` to ``b`` picking the bend that crosses fewest obstacles.

    Two L options exist for non-colinear endpoints: HV (horizontal-first,
    bend at ``(b.x, a.y)``) and VH (vertical-first, bend at ``(a.x, b.y)``).
    This picks whichever crosses fewer ``obstacles`` (axis-aligned bboxes
    given as ``(x_min, y_min, x_max, y_max)``). Ties go to HV so legacy
    behavior is preserved on obstacle-free graphs.
    """
    ax, ay = snap_to_grid(a)
    bx, by = snap_to_grid(b)
    if ax == bx or ay == by:
        return [Wire(ax, ay, bx, by)]

    hv = [((ax, ay), (bx, ay)), ((bx, ay), (bx, by))]
    vh = [((ax, ay), (ax, by)), ((ax, by), (bx, by))]
    hv_cost = sum(_segment_crossings(s, obstacles) for s in hv)
    vh_cost = sum(_segment_crossings(s, obstacles) for s in vh)

    chosen = hv if hv_cost <= vh_cost else vh
    return [Wire(s[0][0], s[0][1], s[1][0], s[1][1]) for s in chosen]
