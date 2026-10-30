"""Agent unit tests — mock the vision_call entirely."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from wirewright.experiments.eeschematic.agent import _extract_json, place
from wirewright.experiments.eeschematic.openai_client import CallResult
from wirewright.ir.model import Component, Net, Schematic
from wirewright.placers.base import PlacerEngineError


def _two_res() -> Schematic:
    return Schematic(
        components=[
            Component(ref="R1", symbol="res", value="10k", pins={"1": "vin", "2": "n1"}),
            Component(ref="R2", symbol="res", value="10k", pins={"1": "n1", "2": "0"}),
            Component(ref="V1", symbol="voltage", value="DC 5", pins={"+": "vin", "-": "0"}),
        ],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
    )


def _fake(text: str, cost: float = 0.001) -> CallResult:
    return CallResult(
        text=text,
        model="mock",
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=cost,
        finish_reason="stop",
    )


def test_extract_json_plain() -> None:
    data = _extract_json('{"componentInstances": [{"name": "R1"}]}')
    assert data["componentInstances"][0]["name"] == "R1"


def test_extract_json_fenced() -> None:
    data = _extract_json('```json\n{"componentInstances": []}\n```')
    assert data == {"componentInstances": []}


def test_extract_json_raises_on_no_json() -> None:
    with pytest.raises(ValueError):
        _extract_json("no json here at all")


def test_place_single_iter_done(tmp_path: Path) -> None:
    """One successful call returning DONE short-circuits the loop."""
    sch = _two_res()
    good_json = {
        "componentInstances": [
            {"name": "V1", "origin": {"x": -4, "y": 4}, "rotation": "0", "flip": "none"},
            {"name": "R1", "origin": {"x": 4, "y": 4}, "rotation": "0", "flip": "none"},
            {"name": "R2", "origin": {"x": 4, "y": -4}, "rotation": "0", "flip": "none"},
        ]
    }
    response = json.dumps(good_json) + "\nDONE\n"
    with patch(
        "wirewright.experiments.eeschematic.agent.vision_call",
        return_value=_fake(response),
    ) as mock:
        out = place(sch, max_iters=3, workdir=tmp_path)
    assert mock.call_count == 1
    placed_refs = {c.ref for c in out.components if c.is_placed}
    assert placed_refs == {"V1", "R1", "R2"}


def test_place_budget_cap(tmp_path: Path) -> None:
    sch = _two_res()
    response = '{"componentInstances":[]}'
    with (
        patch(
            "wirewright.experiments.eeschematic.agent.vision_call",
            return_value=_fake(response, cost=50.0),
        ),
        pytest.raises(PlacerEngineError, match="budget"),
    ):
        place(sch, max_iters=5, budget_usd=10.0, workdir=tmp_path)


def test_place_no_valid_output_raises(tmp_path: Path) -> None:
    sch = _two_res()
    response = "garbage no json"
    with (
        patch(
            "wirewright.experiments.eeschematic.agent.vision_call",
            return_value=_fake(response),
        ),
        pytest.raises(PlacerEngineError, match="no valid placement"),
    ):
        place(sch, max_iters=2, workdir=tmp_path)
