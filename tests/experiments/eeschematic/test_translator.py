"""Translator unit tests — no network, no OpenAI."""

from __future__ import annotations

from wirewright.experiments.eeschematic.translator import (
    EE_UNIT_IN_IR,
    _flip_rotation_to_orientation,
    _normalize_rotation,
    eeschematic_json_to_ir,
)
from wirewright.ir.model import Component, Net, Schematic


def _two_res() -> Schematic:
    return Schematic(
        components=[
            Component(ref="R1", symbol="res", value="10k", pins={"1": "vin", "2": "n1"}),
            Component(ref="R2", symbol="res", value="10k", pins={"1": "n1", "2": "0"}),
        ],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
    )


def test_normalize_rotation_int_and_str() -> None:
    assert _normalize_rotation("90") == 90
    assert _normalize_rotation(180) == 180
    assert _normalize_rotation(None) == 0
    assert _normalize_rotation("garbage") == 0
    assert _normalize_rotation(45) in (0, 90)  # snap


def test_flip_rotation_maps() -> None:
    assert _flip_rotation_to_orientation("none", "0") == "R0"
    assert _flip_rotation_to_orientation("none", "90") == "R90"
    assert _flip_rotation_to_orientation("horizontal", "0") == "M0"
    assert _flip_rotation_to_orientation("horizontal", "90") == "M90"
    assert _flip_rotation_to_orientation("vertical", "0") == "M180"
    assert _flip_rotation_to_orientation("vertical", "90") == "M270"


def test_translate_places_components_by_ref() -> None:
    s = _two_res()
    data = {
        "componentInstances": [
            {"name": "R1", "origin": {"x": 0, "y": 10}, "rotation": "0", "flip": "none"},
            {"name": "R2", "origin": {"x": 0, "y": -10}, "rotation": "0", "flip": "none"},
        ]
    }
    out = eeschematic_json_to_ir(s, data)
    r1 = next(c for c in out.components if c.ref == "R1")
    r2 = next(c for c in out.components if c.ref == "R2")
    assert r1.x == 0 and r1.y == -10 * EE_UNIT_IN_IR  # Y flip
    assert r2.x == 0 and r2.y == 10 * EE_UNIT_IN_IR
    assert r1.orientation == "R0"


def test_translate_ignores_vdd_gnd_placeholders() -> None:
    s = _two_res()
    data = {
        "componentInstances": [
            {"typeName": "VDD", "name": "VDD", "origin": {"x": 0, "y": 20}},
            {"typeName": "GND", "name": "GND1", "origin": {"x": 0, "y": -20}},
            {"name": "R1", "origin": {"x": 0, "y": 10}, "rotation": "0", "flip": "none"},
        ]
    }
    out = eeschematic_json_to_ir(s, data)
    refs = {c.ref for c in out.components}
    assert refs == {"R1", "R2"}  # no VDD/GND created


def test_translate_places_real_vdd_voltage_source() -> None:
    """Regression for 2026-11-16: a wirewright voltage source whose user-
    given ref is 'VDD' (common in bipolar fixtures) must be placed when
    the model emits an instance with that name — the translator must
    NOT skip it as a rail placeholder.
    """
    s = Schematic(
        components=[
            Component(
                ref="VDD",
                symbol="voltage",
                value="DC 12",
                pins={"+": "VDD", "-": "0"},
            ),
            Component(ref="R1", symbol="res", value="1k", pins={"1": "VDD", "2": "0"}),
        ],
        nets=[Net("VDD", is_power=True), Net("0", is_ground=True)],
    )
    data = {
        "componentInstances": [
            {
                "typeName": "voltage",
                "name": "VDD",
                "origin": {"x": -4, "y": 4},
                "rotation": "0",
                "flip": "none",
            },
            {
                "name": "R1",
                "origin": {"x": 0, "y": 0},
                "rotation": "0",
                "flip": "none",
            },
        ]
    }
    out = eeschematic_json_to_ir(s, data)
    vdd = next(c for c in out.components if c.ref == "VDD")
    assert vdd.is_placed, "component with ref='VDD' must be placed, not skipped"
    assert vdd.x == -4 * EE_UNIT_IN_IR
    assert vdd.y == -4 * EE_UNIT_IN_IR  # Y flipped


def test_translate_preserves_input_and_leaves_missing_unplaced() -> None:
    s = _two_res()
    data = {
        "componentInstances": [
            {"name": "R1", "origin": {"x": 1, "y": 1}},
        ]
    }
    out = eeschematic_json_to_ir(s, data)
    # Input unchanged
    assert all(c.x is None for c in s.components)
    # R2 absent from JSON → unplaced
    r2 = next(c for c in out.components if c.ref == "R2")
    assert r2.x is None and r2.y is None


def test_translate_ignores_stray_refs() -> None:
    s = _two_res()
    data = {
        "componentInstances": [
            {"name": "R1", "origin": {"x": 0, "y": 0}},
            {"name": "Q99", "origin": {"x": 10, "y": 10}},  # not in schematic
        ]
    }
    out = eeschematic_json_to_ir(s, data)
    refs = {c.ref for c in out.components}
    assert refs == {"R1", "R2"}
