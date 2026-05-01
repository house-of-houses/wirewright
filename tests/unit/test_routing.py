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
