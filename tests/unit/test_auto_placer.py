"""Tests for AutoPlacer (HOLA → naive fallback)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from wirewright.ir.model import Component, Net, Schematic
from wirewright.placers import AutoPlacer
from wirewright.placers.base import PlacerEngineError
from wirewright.placers.grid_naive import NaivePlacer


def _two_resistor() -> Schematic:
    return Schematic(
        components=[
            Component(ref="R1", symbol="res", value="10k", pins={"1": "vin", "2": "n1"}),
            Component(ref="R2", symbol="res", value="10k", pins={"1": "n1", "2": "0"}),
        ],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
    )


def test_auto_uses_hola_when_it_succeeds() -> None:
    """If HOLA succeeds, the result is HOLA's, not naive's."""
    pytest.importorskip("hola_graph")

    sch = _two_resistor()
    placed_auto = AutoPlacer().place(sch)
    placed_naive = NaivePlacer().place(sch)

    auto_coords = [(c.ref, c.x, c.y) for c in placed_auto.components]
    naive_coords = [(c.ref, c.x, c.y) for c in placed_naive.components]
    assert auto_coords != naive_coords, (
        "auto produced the same layout as naive — HOLA was probably skipped"
    )


def test_auto_falls_back_to_naive_on_hola_engine_error() -> None:
    """If HOLA raises PlacerEngineError, naive's output is returned."""
    sch = _two_resistor()

    def boom(self, schematic, hints=None):  # type: ignore[no-untyped-def]
        raise PlacerEngineError("simulated HOLA abort")

    with patch("wirewright.placers.hola.HolaPlacer.place", boom):
        placed = AutoPlacer().place(sch)

    # Falls back to naive: every component placed, layout matches naive.
    naive = NaivePlacer().place(sch)
    assert [(c.ref, c.x, c.y) for c in placed.components] == [
        (c.ref, c.x, c.y) for c in naive.components
    ]


def test_auto_passes_hints_through() -> None:
    """Pinned hints reach the underlying placer in both branches."""
    sch = _two_resistor()
    pinned = {"R1": (0, 0, "R0")}

    # Force the HOLA branch to fail so naive's pinning behavior is exercised
    # (naive honors pinned; HOLA does not in v0.1).
    def boom(self, schematic, hints=None):  # type: ignore[no-untyped-def]
        raise PlacerEngineError("simulated HOLA abort")

    with patch("wirewright.placers.hola.HolaPlacer.place", boom):
        placed = AutoPlacer().place(sch, hints={"pinned": pinned})

    r1 = placed.component_by_ref("R1")
    assert (r1.x, r1.y) == (0, 0)
