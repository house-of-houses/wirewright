"""End-to-end ELK placer test using the real Node bridge.

Skipped if Node is not installed or elk-bridge dependencies are missing.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from wirewright.ir.model import Component, Net, Schematic
from wirewright.placers.elk import ElkPlacer

_BRIDGE = Path(__file__).resolve().parents[2] / "tools/elk-bridge"


def _bridge_available() -> bool:
    return shutil.which("node") is not None and (_BRIDGE / "node_modules" / "elkjs").is_dir()


@pytest.mark.skipif(not _bridge_available(), reason="elk-bridge not set up")
def test_elk_places_two_resistors_end_to_end() -> None:
    sch = Schematic(
        components=[
            Component(ref="R1", symbol="res", value="10k", pins={"1": "vin", "2": "n1"}),
            Component(ref="R2", symbol="res", value="10k", pins={"1": "n1", "2": "0"}),
        ],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
    )
    placed = ElkPlacer().place(sch)
    assert placed.is_placed
    refs = {c.ref for c in placed.components}
    assert refs == {"R1", "R2"}
    for c in placed.components:
        assert c.x is not None and c.x % 16 == 0
        assert c.y is not None and c.y % 16 == 0
