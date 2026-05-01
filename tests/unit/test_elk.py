"""Tests for the ELK placer's pure IR↔ELK JSON conversion."""

from __future__ import annotations

import pytest

from wirewright.ir.model import Component, Net, Schematic
from wirewright.placers.base import PlacerError
from wirewright.placers.elk import _elk_to_placed_schematic, _ir_to_elk_graph, _port_side


def _two_resistor() -> Schematic:
    return Schematic(
        components=[
            Component(ref="R1", symbol="res", pins={"1": "a", "2": "b"}),
            Component(ref="R2", symbol="res", pins={"1": "b", "2": "0"}),
        ],
        nets=[Net("a"), Net("b"), Net("0", is_ground=True)],
    )


def test_ir_to_elk_emits_one_node_per_component() -> None:
    graph = _ir_to_elk_graph(_two_resistor())
    assert {n["id"] for n in graph["children"]} == {"R1", "R2"}


def test_ir_to_elk_emits_one_port_per_pin() -> None:
    graph = _ir_to_elk_graph(_two_resistor())
    r1 = next(c for c in graph["children"] if c["id"] == "R1")
    assert {p["id"] for p in r1["ports"]} == {"R1.1", "R1.2"}


def test_ir_to_elk_omits_ground_edges() -> None:
    graph = _ir_to_elk_graph(_two_resistor())
    edge_endpoints = {p for e in graph["edges"] for p in e["sources"] + e["targets"]}
    # R2.pin2 maps to ground net "0"; should not appear in any edge.
    assert "R2.2" not in edge_endpoints


def test_ir_to_elk_emits_simple_edge_per_pin_pair() -> None:
    graph = _ir_to_elk_graph(_two_resistor())
    # Net "b" connects R1.2 and R2.1 → 1 simple edge.
    # ELK Layered requires simple edges (one source, one target).
    assert len(graph["edges"]) == 1
    e = graph["edges"][0]
    assert e["sources"] == ["R1.2"]
    assert e["targets"] == ["R2.1"]


def test_ir_to_elk_uses_fixed_pos_with_explicit_port_xy() -> None:
    graph = _ir_to_elk_graph(_two_resistor())
    r1 = next(c for c in graph["children"] if c["id"] == "R1")
    assert r1["properties"]["portConstraints"] == "FIXED_POS"
    # res bbox (0, 16, 32, 96); pin 1 (16, 16) → port (16-0, 16-16) = (16, 0).
    p1 = next(p for p in r1["ports"] if p["id"] == "R1.1")
    assert (p1["x"], p1["y"]) == (16, 0)


def test_ir_to_elk_grid_aligned_spacing() -> None:
    graph = _ir_to_elk_graph(_two_resistor())
    spacing = int(graph["layoutOptions"]["elk.spacing.nodeNode"])
    assert spacing % 16 == 0


def test_port_side_for_resistor_pins() -> None:
    # res pins (16, 16) and (16, 96) in bbox (0, 16, 32, 96).
    # Pin 1 sits on the top edge; pin 2 on the bottom edge.
    assert _port_side("res", "1") == "NORTH"
    assert _port_side("res", "2") == "SOUTH"


def test_port_side_for_mosfet_gate() -> None:
    # nmos gate at (0, 80) in bbox (0, 0, 48, 96); closest edge is WEST.
    assert _port_side("nmos", "G") == "WEST"


def test_port_side_for_bjt_base() -> None:
    # npn base at (0, 48) in bbox (0, 0, 64, 96); closest edge WEST.
    assert _port_side("npn", "B") == "WEST"


def test_port_side_for_opamp2_out() -> None:
    # opamp2 OUT at (32, 64) in bbox (-32, 32, 32, 96); closest edge EAST.
    assert _port_side("opamp2", "OUT") == "EAST"


def test_unknown_symbol_raises_placer_error() -> None:
    s = Schematic(
        components=[Component(ref="X1", symbol="not_real", pins={"a": "n1"})],
        nets=[Net("n1")],
    )
    with pytest.raises(PlacerError, match="unknown symbol"):
        _ir_to_elk_graph(s)


def test_elk_to_placed_applies_coordinates() -> None:
    sch = _two_resistor()
    elk_result = {
        "children": [
            {"id": "R1", "x": 64, "y": 64},
            {"id": "R2", "x": 256, "y": 64},
        ],
        "edges": [
            {
                "id": "e0",
                "sections": [
                    {
                        "startPoint": {"x": 80, "y": 160},
                        "endPoint": {"x": 272, "y": 80},
                        "bendPoints": [{"x": 272, "y": 160}],
                    }
                ],
            }
        ],
    }
    placed = _elk_to_placed_schematic(sch, elk_result)
    r1 = placed.component_by_ref("R1")
    # res bbox (0, 16, 32, 96): node y=64 → component.y = 64 - 16 = 48.
    assert (r1.x, r1.y, r1.orientation) == (64, 48, "R0")
    assert len(placed.wires) >= 1
    # Ground flag for net "0" at R2.pin2.
    assert any(f.net == "0" for f in placed.flags)
