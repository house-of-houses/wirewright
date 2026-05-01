"""Render canonical fixtures via HOLA and verify placement + .asc validity."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

pytest.importorskip("hola_graph")

from wirewright.emit.asc import emit_asc
from wirewright.parse.ltspice_asc import parse_asc_text
from wirewright.parse.spice import parse_spice_file
from wirewright.placers.hola import HolaPlacer


@pytest.mark.parametrize(
    "fixture_relpath",
    [
        "easy/divider.net",
        "medium/tb303-envelope.net",
        # hard fixture deliberately excluded: hola-graph's C++ aborts on this
        # graph topology (faces.cpp:identifyExternalFace assertion). Python
        # cannot catch the abort; subprocess isolation deferred to v0.2.
    ],
)
def test_hola_renders_canonical_fixture(fixture_relpath: str) -> None:
    """Phase 4 DoD: each canonical fixture renders to a valid placed Schematic
    (or raises PlacerEngineError for non-planar circuits — known v0.1 HOLA
    limitation, the assertion-failure-in-faces.cpp case). Strict connectivity
    is NOT checked for HOLA; bare HOLA placement + naive pairwise L-shape
    routing produces wire overlaps even on tiny fixtures because HOLA has no
    port-side awareness. v0.2 may explore libdialect's port-aware variant.
    """
    from wirewright.placers.base import PlacerEngineError

    fixture = Path(__file__).resolve().parents[2] / "tests/fixtures" / fixture_relpath
    if not fixture.exists():
        pytest.skip(f"fixture not present: {fixture_relpath}")

    parsed_input = parse_spice_file(cast(Path, fixture))
    try:
        placed = HolaPlacer().place(parsed_input)
    except PlacerEngineError as e:
        if "non-planar" in str(e):
            pytest.skip(f"HOLA cannot handle non-planar graph: {fixture_relpath}")
        raise

    assert placed.is_placed
    assert {c.ref for c in placed.components} == {c.ref for c in parsed_input.components}

    asc_text = emit_asc(placed)
    reparsed = parse_asc_text(asc_text)
    assert {c.ref for c in reparsed.components} == {c.ref for c in placed.components}
