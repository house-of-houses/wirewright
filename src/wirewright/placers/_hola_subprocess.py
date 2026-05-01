"""Standalone HOLA layout runner.

Reads a JSON graph from stdin, calls ``hola_graph.HolaGraph.layout()``, and
writes a JSON result to stdout. Designed to be invoked as a subprocess so
HOLA's C++ asserts in ``faces.cpp`` (which abort the process) don't kill
the parent Python interpreter.

Input JSON (stdin)::

    {
      "nodes": [{"label": "R1", "width": 32, "height": 80}, ...],
      "edges": [["R1", "R2"], ...]   // pairs of labels
    }

Output JSON (stdout)::

    {
      "R1": {"x": 64.0, "y": 12.0, "left": 48.0, "top": -28.0,
             "right": 80.0, "bottom": 52.0},
      ...
    }

Non-zero exit (negative for signal, e.g. SIGABRT=-6) indicates the layout
failed; the parent should raise ``PlacerEngineError``.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    data = json.load(sys.stdin)
    from hola_graph import HolaGraph  # noqa: PLC0415

    g = HolaGraph()
    for node in data["nodes"]:
        g.add_node(
            width=float(node["width"]),
            height=float(node["height"]),
            label=node["label"],
        )
    for src, tgt in data["edges"]:
        g.connect(src, tgt)
    g.layout()

    out: dict[str, dict[str, float]] = {}
    for node in data["nodes"]:
        n = g.node(node["label"])
        left, top, right, bottom = n.bounds
        out[node["label"]] = {
            "x": float(n.x),
            "y": float(n.y),
            "left": float(left),
            "top": float(top),
            "right": float(right),
            "bottom": float(bottom),
        }
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
