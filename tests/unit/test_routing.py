"""Tests for routing/orthogonal.py."""

from __future__ import annotations

from wirewright.routing.orthogonal import l_shape, manhattan_segments, snap_to_grid


def test_snap_rounds_to_grid() -> None:
    assert snap_to_grid((17, 0)) == (16, 0)
    assert snap_to_grid((24, 24)) == (32, 32)
    assert snap_to_grid((-9, 7)) == (-16, 0)


def test_l_shape_colinear_x() -> None:
    wires = l_shape((80, 64), (80, 160))
    assert len(wires) == 1
    assert (wires[0].x1, wires[0].y1, wires[0].x2, wires[0].y2) == (80, 64, 80, 160)


def test_l_shape_colinear_y() -> None:
    wires = l_shape((80, 64), (272, 64))
    assert len(wires) == 1


def test_l_shape_bends() -> None:
    wires = l_shape((80, 80), (272, 160))
    assert len(wires) == 2
    # Horizontal first.
    assert (wires[0].y1, wires[0].y2) == (80, 80)
    assert (wires[1].x1, wires[1].x2) == (272, 272)


def test_manhattan_chain() -> None:
    pts = [(0, 0), (32, 0), (32, 64)]
    wires = manhattan_segments(pts)
    assert len(wires) == 2


def test_l_shape_avoiding_prefers_unobstructed_bend() -> None:
    from wirewright.routing.orthogonal import l_shape_avoiding

    # Endpoints (0, 0) → (96, 96). HV bend at (96, 0); VH bend at (0, 96).
    # Obstacle covers the HV bend column at top: bbox (32, -16, 80, 16).
    # The HV horizontal segment (0,0)-(96,0) crosses that obstacle.
    obstacles = [(32, -16, 80, 16)]
    wires = l_shape_avoiding((0, 0), (96, 96), obstacles)
    bend = (wires[0].x2, wires[0].y2)
    assert bend == (0, 96)


def test_l_shape_avoiding_falls_back_to_hv_on_tie() -> None:
    from wirewright.routing.orthogonal import l_shape_avoiding

    wires = l_shape_avoiding((0, 0), (96, 96), [])
    assert (wires[0].x2, wires[0].y2) == (96, 0)


def test_l_shape_avoiding_colinear_returns_single_segment() -> None:
    from wirewright.routing.orthogonal import l_shape_avoiding

    wires = l_shape_avoiding((0, 64), (96, 64), [(32, 32, 80, 80)])
    assert len(wires) == 1
