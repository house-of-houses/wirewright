"""Unit tests for the EEschematic renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from wirewright.ir.model import Component, Flag, Net, Schematic, Wire

matplotlib = pytest.importorskip("matplotlib")

from wirewright.experiments.eeschematic.render import render_schematic_png  # noqa: E402


def _two_resistor_placed() -> Schematic:
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
    return Schematic(
        components=[r1, r2],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
        wires=[Wire(80, 160, 80, 208)],  # between R1 pin 2 and R2 pin 1
        flags=[Flag(80, 288, "0"), Flag(80, 48, "vin")],
    )


def test_renders_png(tmp_path: Path) -> None:
    out = tmp_path / "div.png"
    render_schematic_png(_two_resistor_placed(), out)
    assert out.exists()
    assert out.stat().st_size > 500  # non-trivial PNG


def test_renders_empty_schematic(tmp_path: Path) -> None:
    """Empty inputs must not crash — used by the agent on the very first call."""
    out = tmp_path / "empty.png"
    render_schematic_png(
        Schematic(components=[], nets=[], wires=[], flags=[]),
        out,
    )
    assert out.exists()


def test_output_is_deterministic(tmp_path: Path) -> None:
    """Same input → identical bytes."""
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    render_schematic_png(_two_resistor_placed(), a)
    render_schematic_png(_two_resistor_placed(), b)
    assert a.read_bytes() == b.read_bytes()


def test_renders_rotated_component(tmp_path: Path) -> None:
    """Non-R0 orientation path exercised."""
    r90 = Component(
        ref="R1",
        symbol="res",
        value="1k",
        pins={"1": "a", "2": "b"},
        x=128,
        y=128,
        orientation="R90",
    )
    sch = Schematic(
        components=[r90],
        nets=[Net("a"), Net("b")],
    )
    out = tmp_path / "rotated.png"
    render_schematic_png(sch, out)
    assert out.exists()
