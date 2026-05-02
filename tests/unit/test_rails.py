"""Tests for the power/ground rail synthesis helper."""

from __future__ import annotations

from wirewright.ir.model import Component, Net, Schematic
from wirewright.routing.rails import emit_power_ground_rails


def _two_resistor_with_ground() -> Schematic:
    """R1, R2 in series. R2 pin 2 grounded. Both resistors placed."""
    return Schematic(
        components=[
            Component(
                ref="R1",
                symbol="res",
                pins={"1": "vin", "2": "n1"},
                x=64,
                y=64,
                orientation="R0",
            ),
            Component(
                ref="R2",
                symbol="res",
                pins={"1": "n1", "2": "0"},
                x=256,
                y=64,
                orientation="R0",
            ),
        ],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
    )


def test_emit_rails_for_ground_only() -> None:
    sch = _two_resistor_with_ground()
    _wires, flags = emit_power_ground_rails(sch)

    # Exactly one ground FLAG at the rail's terminus.
    ground_flags = [f for f in flags if f.net == "0"]
    assert len(ground_flags) == 1


def test_emit_rails_no_components_returns_empty() -> None:
    sch = Schematic(components=[], nets=[Net("0", is_ground=True)])
    wires, flags = emit_power_ground_rails(sch)
    assert wires == []
    assert flags == []


def test_emit_rails_no_ground_or_power_returns_empty() -> None:
    sch = Schematic(
        components=[
            Component(
                ref="R1",
                symbol="res",
                pins={"1": "a", "2": "b"},
                x=64,
                y=64,
                orientation="R0",
            ),
        ],
        nets=[Net("a"), Net("b")],
    )
    wires, flags = emit_power_ground_rails(sch)
    assert wires == []
    assert flags == []


def test_emit_rails_for_power_net() -> None:
    sch = Schematic(
        components=[
            Component(
                ref="R1",
                symbol="res",
                pins={"1": "vcc", "2": "out"},
                x=64,
                y=64,
                orientation="R0",
            ),
            Component(
                ref="R2",
                symbol="res",
                pins={"1": "vcc", "2": "out2"},
                x=256,
                y=64,
                orientation="R0",
            ),
        ],
        nets=[Net("vcc", is_power=True), Net("out"), Net("out2")],
    )
    _wires, flags = emit_power_ground_rails(sch)
    vcc_flags = [f for f in flags if f.net == "vcc"]
    assert len(vcc_flags) == 1
    # Power rail flag should be ABOVE the components (smaller y in canvas coords).
    assert vcc_flags[0].y < 64
