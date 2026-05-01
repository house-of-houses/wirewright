"""Tests for placement back ends.

The ``TestAnyPlacer`` class is parameterized over every placer in the registry
that does not require optional native dependencies. Its tests assert the
universal contract from docs/specs/placer-interface.md. Every placer must pass.

Back-end-specific tests live in their own classes.
"""

from __future__ import annotations

import copy

import pytest

from wirewright.ir.model import Component, Net, Schematic
from wirewright.ir.validate import LTSPICE_GRID, validate_placed
from wirewright.placers import NaivePlacer, get_placer
from wirewright.placers.base import Placer

# Placers safe to test without external dependencies (no Node, no pyhola).
PURE_PLACERS: list[type[Placer]] = [NaivePlacer]


def _two_resistors() -> Schematic:
    return Schematic(
        components=[
            Component(ref="R1", symbol="res", value="10k", pins={"1": "a", "2": "b"}),
            Component(ref="R2", symbol="res", value="10k", pins={"1": "b", "2": "0"}),
        ],
        nets=[Net("a"), Net("b"), Net("0", is_ground=True)],
    )


@pytest.fixture(params=PURE_PLACERS, ids=lambda c: c.name)
def placer(request: pytest.FixtureRequest) -> Placer:
    return request.param()


class TestAnyPlacer:
    """Contract tests every placer must pass."""

    def test_places_every_component(self, placer: Placer) -> None:
        out = placer.place(_two_resistors())
        for c in out.components:
            assert c.is_placed, f"{c.ref!r} was not placed"

    def test_does_not_mutate_input(self, placer: Placer) -> None:
        s = _two_resistors()
        original = copy.deepcopy(s)
        placer.place(s)
        assert s == original

    def test_output_passes_validation(self, placer: Placer) -> None:
        out = placer.place(_two_resistors())
        validate_placed(out)  # raises if invalid

    def test_grid_aligned(self, placer: Placer) -> None:
        out = placer.place(_two_resistors())
        for c in out.components:
            assert c.x is not None and c.y is not None
            assert c.x % LTSPICE_GRID == 0
            assert c.y % LTSPICE_GRID == 0

    def test_deterministic(self, placer: Placer) -> None:
        s = _two_resistors()
        a = placer.place(s)
        b = placer.place(s)
        assert [(c.ref, c.x, c.y, c.orientation) for c in a.components] == [
            (c.ref, c.x, c.y, c.orientation) for c in b.components
        ]

    def test_no_overlap(self, placer: Placer) -> None:
        out = placer.place(_two_resistors())
        positions = {(c.x, c.y) for c in out.components}
        assert len(positions) == len(out.components), "components share an origin"


class TestRegistryLookup:
    def test_lookup_naive(self) -> None:
        p = get_placer("naive")
        assert isinstance(p, NaivePlacer)

    def test_lookup_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown placer"):
            get_placer("nope")
