"""Tests for the HOLA placer."""

from __future__ import annotations

import pytest

pytest.importorskip("hola_graph")

from wirewright.ir.model import Component, Net, Schematic
from wirewright.placers.base import PlacerError
from wirewright.placers.hola import HolaPlacer


def _two_resistor() -> Schematic:
    return Schematic(
        components=[
            Component(ref="R1", symbol="res", value="10k", pins={"1": "vin", "2": "n1"}),
            Component(ref="R2", symbol="res", value="10k", pins={"1": "n1", "2": "0"}),
        ],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
    )


def test_hola_places_every_component() -> None:
    placed = HolaPlacer().place(_two_resistor())
    assert placed.is_placed


def test_hola_grid_aligned() -> None:
    placed = HolaPlacer().place(_two_resistor())
    for c in placed.components:
        assert c.x is not None and c.x % 16 == 0
        assert c.y is not None and c.y % 16 == 0


def test_hola_does_not_mutate_input() -> None:
    s = _two_resistor()
    HolaPlacer().place(s)
    for c in s.components:
        assert c.x is None and c.y is None


def test_hola_emits_ground_flags() -> None:
    placed = HolaPlacer().place(_two_resistor())
    assert any(f.net == "0" for f in placed.flags)


def test_hola_unknown_symbol_raises_placer_error() -> None:
    s = Schematic(
        components=[Component(ref="X1", symbol="not_real", pins={"a": "n1"})],
        nets=[Net("n1")],
    )
    with pytest.raises(PlacerError, match="unknown symbol"):
        HolaPlacer().place(s)


def test_hola_deterministic() -> None:
    s = _two_resistor()
    a = HolaPlacer().place(s)
    b = HolaPlacer().place(s)
    assert [(c.ref, c.x, c.y, c.orientation) for c in a.components] == [
        (c.ref, c.x, c.y, c.orientation) for c in b.components
    ]


def test_biconnect_leaf_extras_chains_leaves_per_articulation_point() -> None:
    from wirewright.placers.hola import _biconnect_leaf_extras

    # Two articulation points (cut1, cut2) each holding leaves.
    # cut1 → [a, b, c]; cut2 → [d, e]; cut1↔cut2 is the bridging edge.
    edges = [
        ("cut1", "a"),
        ("cut1", "b"),
        ("cut1", "c"),
        ("cut1", "cut2"),
        ("cut2", "d"),
        ("cut2", "e"),
    ]
    nodes = ["cut1", "cut2", "a", "b", "c", "d", "e"]
    extras = _biconnect_leaf_extras(nodes, edges)
    # Chains a-b-c around cut1 (2 edges) and d-e around cut2 (1 edge).
    assert len(extras) == 3
    pairs = {tuple(sorted(e)) for e in extras}
    assert pairs == {("a", "b"), ("b", "c"), ("d", "e")}


def test_biconnect_leaf_extras_empty_when_no_articulation_leaves() -> None:
    from wirewright.placers.hola import _biconnect_leaf_extras

    # A simple cycle has no articulation points.
    extras = _biconnect_leaf_extras(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")])
    assert extras == []
