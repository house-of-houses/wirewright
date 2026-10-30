"""Divider prove-out: end-to-end plumbing of the EEschematic placer.

Structural oracle (no hand-drawn .asc reference exists for divider):

1. Output passes ``validate_placed`` — integer grid coords, no overlaps,
   axis-aligned wires, pin endpoints exact.
2. Component set is unchanged (same refs, same symbols, same values).
3. Connectivity is isomorphic to the parsed netlist's net graph.

This test is marked ``openai_live`` and runs only when OPENAI_API_KEY and
WIREWRIGHT_RUN_LIVE_LLM=1 are set (see tests/experiments/conftest.py).
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pytest

from wirewright.ir.validate import validate_placed
from wirewright.parse.spice import parse_spice_text

FIXTURE = Path(__file__).parents[3] / "tests" / "fixtures" / "easy" / "divider.net"


def _net_graph(components, nets):
    """Bipartite component <-> net graph used as structural oracle."""
    g = nx.Graph()
    for c in components:
        g.add_node(("C", c.ref))
    for n in nets:
        g.add_node(("N", n.name))
    for c in components:
        for net_name in c.pins.values():
            g.add_edge(("C", c.ref), ("N", net_name))
    return g


@pytest.mark.openai_live
def test_divider_end_to_end_produces_valid_ir() -> None:
    from wirewright.placers.eeschematic import EEschematicPlacer

    original = parse_spice_text(FIXTURE.read_text())
    placed = EEschematicPlacer().place(original)

    # 1. Validation
    validate_placed(placed)

    # 2. Component identity preserved
    orig_refs = {(c.ref, c.symbol, c.value) for c in original.components}
    out_refs = {(c.ref, c.symbol, c.value) for c in placed.components}
    assert orig_refs == out_refs

    # 3. Connectivity isomorphism
    g_in = _net_graph(original.components, original.nets)
    g_out = _net_graph(placed.components, placed.nets)
    assert nx.is_isomorphic(
        g_in,
        g_out,
        node_match=lambda a, b: a == b,
    )
