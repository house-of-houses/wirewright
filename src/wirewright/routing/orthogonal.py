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

    For multi-obstacle situations where both L options cross something,
    use :func:`route_avoiding` instead — it tries Z-shape detours around
    the obstacle bbox extremes.
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


def _point_on_segment_closed(
    point: tuple[int, int],
    seg: tuple[tuple[int, int], tuple[int, int]],
) -> bool:
    """True if ``point`` lies anywhere on the closed axis-aligned segment."""
    px, py = point
    (x1, y1), (x2, y2) = seg
    if x1 == x2:
        if px != x1:
            return False
        return min(y1, y2) <= py <= max(y1, y2)
    if py != y1:
        return False
    return min(x1, x2) <= px <= max(x1, x2)


def _pin_hits(
    seg: tuple[tuple[int, int], tuple[int, int]],
    pin_obstacles: list[tuple[int, int]],
) -> int:
    """Count pin obstacles whose position lies on the segment."""
    return sum(1 for p in pin_obstacles if _point_on_segment_closed(p, seg))


def _path_score(
    path: list[tuple[int, int]],
    obstacles: list[tuple[int, int, int, int]],
    pin_obstacles: list[tuple[int, int]] | None = None,
) -> tuple[int, int, int]:
    """Score ``(pin_hits, bbox_crossings, total_length)``. Lower is better.

    A pin hit is any wire segment that passes through a pin position on
    a different net — causes an electrical short in LTspice. Weighted
    strictly above bbox crossings so the min() always prefers a short-
    free path, then a bbox-free path, then the shortest.
    """
    bbox_crossings = 0
    pins = 0
    length = 0
    pin_obstacles = pin_obstacles or []
    for i in range(len(path) - 1):
        seg = (path[i], path[i + 1])
        bbox_crossings += _segment_crossings(seg, obstacles)
        pins += _pin_hits(seg, pin_obstacles)
        length += abs(path[i + 1][0] - path[i][0]) + abs(path[i + 1][1] - path[i][1])
    return pins, bbox_crossings, length


def route_avoiding(
    a: tuple[int, int],
    b: tuple[int, int],
    obstacles: list[tuple[int, int, int, int]],
    pin_obstacles: list[tuple[int, int]] | None = None,
) -> list[Wire]:
    """Manhattan-route ``a`` to ``b`` avoiding obstacle bboxes and pin shorts.

    Tries L-shape (2 options); if both cross obstacles, also tries 4
    Z-shape detours that route around the obstacle-bbox extremes (above,
    below, left of, right of *all* obstacles). Picks the path with
    minimum ``(pin_hits, bbox_crossings, total_length)``. Empty obstacle
    list reduces to standard L-shape with HV preference.

    ``pin_obstacles`` are pin positions of OTHER nets. A segment passing
    through such a pin (at corner or interior) would short two nets in
    LTspice. The caller must exclude ``a`` and ``b`` themselves — they
    are pins of the net being routed and are the legitimate endpoints.
    """
    ax, ay = snap_to_grid(a)
    bx, by = snap_to_grid(b)

    # Colinear endpoints: the straight segment is the obvious answer,
    # but only if no pin obstacle sits on it. Pin shorts take priority
    # over path simplicity — if a straight stub would short two nets,
    # add bump-out detour candidates that go one grid step aside.
    if ax == bx or ay == by:
        straight = [(ax, ay), (bx, by)]
        if not pin_obstacles or not any(
            _point_on_segment_closed(p, (straight[0], straight[1])) for p in pin_obstacles
        ):
            return [Wire(ax, ay, bx, by)]
        # Build bump-out candidates. For a vertical straight (ax == bx),
        # detour via x ± LTSPICE_GRID. For a horizontal straight, via
        # y ± LTSPICE_GRID.
        candidates: list[list[tuple[int, int]]] = []
        if ax == bx:
            for dx in (LTSPICE_GRID, -LTSPICE_GRID):
                candidates.append(
                    [(ax, ay), (ax + dx, ay), (ax + dx, by), (bx, by)]
                )
        else:
            for dy in (LTSPICE_GRID, -LTSPICE_GRID):
                candidates.append(
                    [(ax, ay), (ax, ay + dy), (bx, by + dy), (bx, by)]
                )
        best = min(candidates, key=lambda p: _path_score(p, obstacles, pin_obstacles))
        bump_wires: list[Wire] = []
        for i in range(len(best) - 1):
            if best[i] != best[i + 1]:
                bump_wires.append(
                    Wire(best[i][0], best[i][1], best[i + 1][0], best[i + 1][1])
                )
        return bump_wires

    candidates = [
        [(ax, ay), (bx, ay), (bx, by)],  # HV (horizontal-first L)
        [(ax, ay), (ax, by), (bx, by)],  # VH (vertical-first L)
    ]

    # Any avoidance target (bbox or pin) triggers Z-detour candidates.
    # Pin obstacles are included in the extreme calculation as 0-size
    # bboxes so detour lanes clear them too.
    if obstacles or pin_obstacles:
        margin = LTSPICE_GRID
        all_bboxes: list[tuple[int, int, int, int]] = list(obstacles)
        if pin_obstacles:
            all_bboxes.extend((p[0], p[1], p[0], p[1]) for p in pin_obstacles)
        all_x_min = min(o[0] for o in all_bboxes) - margin
        all_y_min = min(o[1] for o in all_bboxes) - margin
        all_x_max = max(o[2] for o in all_bboxes) + margin
        all_y_max = max(o[3] for o in all_bboxes) + margin
        top_y = snap_to_grid((0, all_y_min))[1]
        bot_y = snap_to_grid((0, all_y_max))[1]
        left_x = snap_to_grid((all_x_min, 0))[0]
        right_x = snap_to_grid((all_x_max, 0))[0]

        # Z-above: vertical → horizontal-above-everything → vertical-down → horizontal-to-b.
        candidates.append([(ax, ay), (ax, top_y), (bx, top_y), (bx, by)])
        # Z-below
        candidates.append([(ax, ay), (ax, bot_y), (bx, bot_y), (bx, by)])
        # Z-left
        candidates.append([(ax, ay), (left_x, ay), (left_x, by), (bx, by)])
        # Z-right
        candidates.append([(ax, ay), (right_x, ay), (right_x, by), (bx, by)])

    best = min(candidates, key=lambda p: _path_score(p, obstacles, pin_obstacles))

    wires: list[Wire] = []
    for i in range(len(best) - 1):
        if best[i] != best[i + 1]:
            wires.append(Wire(best[i][0], best[i][1], best[i + 1][0], best[i + 1][1]))
    return wires
