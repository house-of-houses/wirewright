"""Unit tests for the wiring post-pass."""

from __future__ import annotations

from wirewright.experiments.eeschematic.wiring import wire_placed_schematic
from wirewright.ir.model import Component, Net, Schematic
from wirewright.ir.validate import validate_placed


def test_wiring_produces_valid_divider() -> None:
    # Hand-place a 2-resistor divider the way the LLM would.
    r1 = Component(
        ref="R1",
        symbol="res",
        value="10k",
        pins={"1": "vin", "2": "n1"},
        x=64,
        y=64,
        orientation="R0",
    )
    r2 = Component(
        ref="R2",
        symbol="res",
        value="10k",
        pins={"1": "n1", "2": "0"},
        x=64,
        y=192,
        orientation="R0",
    )
    v = Component(
        ref="V1",
        symbol="voltage",
        value="DC 5",
        pins={"+": "vin", "-": "0"},
        x=-64,
        y=64,
        orientation="R0",
    )
    s = Schematic(
        components=[v, r1, r2],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
    )
    out = wire_placed_schematic(s)
    assert len(out.wires) > 0
    validate_placed(out)
