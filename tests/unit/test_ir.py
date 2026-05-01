"""Tests for the IR dataclasses and validation."""

from __future__ import annotations

import pytest

from wirewright.ir.model import Component, Net, Schematic, Wire
from wirewright.ir.validate import ValidationError, validate, validate_placed


def _two_resistors() -> Schematic:
    return Schematic(
        components=[
            Component(ref="R1", symbol="res", pins={"1": "a", "2": "b"}),
            Component(ref="R2", symbol="res", pins={"1": "b", "2": "0"}),
        ],
        nets=[Net("a"), Net("b"), Net("0", is_ground=True)],
    )


def test_pin_construction() -> None:
    s = _two_resistors()
    assert len(s.components) == 2
    assert s.component_by_ref("R1").pins["1"] == "a"


def test_net_lookup() -> None:
    s = _two_resistors()
    assert s.net_by_name("0").is_ground
    with pytest.raises(KeyError):
        s.net_by_name("nope")


def test_validate_unplaced_passes() -> None:
    validate(_two_resistors())  # should not raise


def test_duplicate_refs_rejected() -> None:
    s = Schematic(
        components=[
            Component(ref="R1", symbol="res", pins={"1": "a", "2": "0"}),
            Component(ref="R1", symbol="res", pins={"1": "a", "2": "0"}),
        ],
        nets=[Net("a"), Net("0", is_ground=True)],
    )
    with pytest.raises(ValidationError, match="Duplicate component reference"):
        validate(s)


def test_undeclared_net_rejected() -> None:
    s = Schematic(
        components=[Component(ref="R1", symbol="res", pins={"1": "a", "2": "ghost"})],
        nets=[Net("a")],
    )
    with pytest.raises(ValidationError, match="undeclared net 'ghost'"):
        validate(s)


def test_validate_placed_requires_coordinates() -> None:
    s = _two_resistors()
    with pytest.raises(ValidationError, match="no coordinates after placement"):
        validate_placed(s)


def test_diagonal_wire_rejected() -> None:
    with pytest.raises(ValueError, match="not axis-aligned"):
        Wire(0, 0, 32, 32)


def test_grid_alignment_enforced_after_placement() -> None:
    s = _two_resistors()
    s.components[0].x = 17  # not on grid
    s.components[0].y = 0
    s.components[1].x = 32
    s.components[1].y = 0
    with pytest.raises(ValidationError, match="not on LTspice grid"):
        validate_placed(s)
