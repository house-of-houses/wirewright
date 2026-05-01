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


def test_validate_placed_rejects_bbox_overlap() -> None:
    # Each res bbox is (0, 16, 32, 96). Origins (64, 64) and (64, 80) →
    # bboxes (64, 80, 96, 160) and (64, 96, 96, 176) → overlap.
    s = Schematic(
        components=[
            Component(ref="R1", symbol="res", pins={"1": "a", "2": "b"}, x=64, y=64),
            Component(ref="R2", symbol="res", pins={"1": "b", "2": "0"}, x=64, y=80),
        ],
        nets=[Net("a"), Net("b"), Net("0", is_ground=True)],
    )
    with pytest.raises(ValidationError, match="overlap"):
        validate_placed(s)


def test_validate_placed_accepts_adjacent_bboxes() -> None:
    # Horizontally separated by 64 units; res bbox is 32 wide → no overlap.
    s = Schematic(
        components=[
            Component(ref="R1", symbol="res", pins={"1": "a", "2": "b"}, x=64, y=64),
            Component(ref="R2", symbol="res", pins={"1": "b", "2": "0"}, x=128, y=64),
        ],
        nets=[Net("a"), Net("b"), Net("0", is_ground=True)],
    )
    validate_placed(s)


def test_validate_placed_handles_rotated_bbox_correctly() -> None:
    # res bbox (0, 16, 32, 96) rotated R90 around origin → AABB (-96, 0, -16, 32).
    # R1 at (192, 208) R90 → bbox (96, 208, 176, 240).
    # R2 at (160, 208) R0 → bbox (160, 224, 192, 304).
    # x (96..176) ∩ (160..192) overlaps; y (208..240) ∩ (224..304) overlaps.
    s = Schematic(
        components=[
            Component(
                ref="R1",
                symbol="res",
                pins={"1": "a", "2": "b"},
                x=192,
                y=208,
                orientation="R90",
            ),
            Component(
                ref="R2",
                symbol="res",
                pins={"1": "b", "2": "0"},
                x=160,
                y=208,
                orientation="R0",
            ),
        ],
        nets=[Net("a"), Net("b"), Net("0", is_ground=True)],
    )
    with pytest.raises(ValidationError, match="overlap"):
        validate_placed(s)
