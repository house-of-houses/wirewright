"""ELK (Eclipse Layout Kernel) placer adapter.

Converts an IR :class:`Schematic` to an ELK JSON graph with ``FIXED_POS``
ports, runs the Node.js bridge in ``tools/elk-bridge/``, parses the result
back, snaps to the LTspice grid, and returns a placed Schematic.

Power and ground nets are NOT emitted as ELK edges; they get global rails
(stub wires + FLAGs at every connecting pin) after layout.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from wirewright.ir.model import Flag, Schematic, Wire
from wirewright.ir.validate import LTSPICE_GRID, validate, validate_placed
from wirewright.placers.base import Placer, PlacerEngineError, PlacerError
from wirewright.routing.orthogonal import manhattan_segments, snap_to_grid
from wirewright.symbols.builtin import absolute_pin_position, symbol_geometry

_SIDE_NAMES: dict[str, str] = {"W": "WEST", "E": "EAST", "N": "NORTH", "S": "SOUTH"}


def _bridge_path() -> Path:
    """Resolve the elk-bridge directory relative to this package."""
    return Path(__file__).resolve().parent.parent.parent.parent / "tools/elk-bridge"


def _port_side(symbol: str, pin_name: str) -> str:
    """Closest-edge rule: which bbox edge is the pin nearest to."""
    geo = symbol_geometry(symbol)
    px, py = geo.pins[pin_name]
    x_min, y_min, x_max, y_max = geo.bbox
    distances = {
        "W": px - x_min,
        "E": x_max - px,
        "N": py - y_min,
        "S": y_max - py,
    }
    closest = min(distances, key=lambda k: distances[k])
    return _SIDE_NAMES[closest]


def _ir_to_elk_graph(schematic: Schematic) -> dict[str, Any]:
    """Convert IR Schematic to ELK graph JSON. Pure; no I/O.

    Uses ``FIXED_POS`` per-port (x, y) so ELK edge sections terminate on
    exact pin positions. Multi-pin nets emit a single hyper-edge. Ground
    and power nets are omitted from edges (handled as global rails after
    layout).
    """
    children: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    power_or_ground: set[str] = {n.name for n in schematic.nets if n.is_power or n.is_ground}

    for c in schematic.components:
        try:
            geo = symbol_geometry(c.symbol)
        except KeyError as e:
            raise PlacerError(f"Component {c.ref!r}: unknown symbol {c.symbol!r}") from e
        x_min, y_min, x_max, y_max = geo.bbox
        width = max(x_max - x_min, LTSPICE_GRID)
        height = max(y_max - y_min, LTSPICE_GRID)
        port_specs: list[dict[str, Any]] = []
        for pin_name in c.pins:
            pin_x, pin_y = geo.pins[pin_name]
            port_specs.append(
                {
                    "id": f"{c.ref}.{pin_name}",
                    "x": pin_x - x_min,
                    "y": pin_y - y_min,
                    "properties": {"port.side": _port_side(c.symbol, pin_name)},
                }
            )
        children.append(
            {
                "id": c.ref,
                "width": width,
                "height": height,
                "ports": port_specs,
                "properties": {"portConstraints": "FIXED_POS"},
            }
        )

    net_to_ports: dict[str, list[str]] = {}
    for c in schematic.components:
        for pin_name, net_name in c.pins.items():
            if net_name in power_or_ground:
                continue
            net_to_ports.setdefault(net_name, []).append(f"{c.ref}.{pin_name}")

    # Pairwise edges: ELK Layered requires "simple" edges (1 source, 1 target).
    # A multi-pin net becomes (N-1) edges all anchored to the first port; that
    # produces visually-redundant routes but is the cost of using Layered. A
    # future placer can switch algorithms to use hyper-edges.
    edge_id = 0
    for net_name, ports in net_to_ports.items():
        if len(ports) < 2:
            continue
        anchor = ports[0]
        for target in ports[1:]:
            edges.append(
                {
                    "id": f"e{edge_id}_{net_name}",
                    "sources": [anchor],
                    "targets": [target],
                }
            )
            edge_id += 1

    layout_options = {
        "elk.spacing.nodeNode": str(LTSPICE_GRID * 4),
        "elk.layered.spacing.nodeNodeBetweenLayers": str(LTSPICE_GRID * 6),
    }

    return {
        "id": "root",
        "layoutOptions": layout_options,
        "children": children,
        "edges": edges,
    }


def _elk_to_placed_schematic(schematic: Schematic, elk_result: dict[str, Any]) -> Schematic:
    """Apply ELK output to a copy of the input schematic.

    Snaps node origins to the LTspice grid; reconstructs wires from each
    edge's section bend points; emits ground/power FLAGs.
    """
    out = copy.deepcopy(schematic)
    placed_by_id: dict[str, dict[str, Any]] = {n["id"]: n for n in elk_result.get("children", [])}

    for c in out.components:
        node = placed_by_id.get(c.ref)
        if node is None:
            raise PlacerEngineError(f"ELK did not place component {c.ref!r}")
        geo = symbol_geometry(c.symbol)
        sx, sy = snap_to_grid(
            (
                int(node.get("x", 0)) - geo.bbox[0],
                int(node.get("y", 0)) - geo.bbox[1],
            )
        )
        c.x, c.y = sx, sy
        c.orientation = "R0"

    out.wires = []
    for edge in elk_result.get("edges", []):
        for section in edge.get("sections", []):
            pts: list[tuple[int, int]] = []
            sp = section.get("startPoint")
            if sp:
                pts.append(snap_to_grid((int(sp["x"]), int(sp["y"]))))
            for bp in section.get("bendPoints", []):
                pts.append(snap_to_grid((int(bp["x"]), int(bp["y"]))))
            ep = section.get("endPoint")
            if ep:
                pts.append(snap_to_grid((int(ep["x"]), int(ep["y"]))))
            out.wires.extend(manhattan_segments(pts))

    out.wires = _strip_zero_length_wires(out.wires)

    out.flags = []
    nets_by_name = {n.name: n for n in out.nets}
    for c in out.components:
        assert c.x is not None and c.y is not None, f"{c.ref!r} unplaced"
        for pin_name, net_name in c.pins.items():
            net = nets_by_name.get(net_name)
            if net is None:
                continue
            pos = absolute_pin_position((c.x, c.y), c.symbol, pin_name, c.orientation)
            if net.is_ground or net.name == "0":
                stub_y = pos[1] + LTSPICE_GRID * 2
                out.wires.append(Wire(pos[0], pos[1], pos[0], stub_y))
                out.flags.append(Flag(pos[0], stub_y, "0"))
            elif net.is_power:
                out.flags.append(Flag(pos[0], pos[1], net.name))

    validate_placed(out)
    return out


def _strip_zero_length_wires(wires: list[Wire]) -> list[Wire]:
    """Drop wires whose endpoints are identical after grid snapping."""
    return [w for w in wires if (w.x1, w.y1) != (w.x2, w.y2)]


def _run_bridge(graph: dict[str, Any]) -> dict[str, Any]:
    """Run the Node.js elk-bridge subprocess and parse its stdout."""
    if shutil.which("node") is None:
        raise PlacerEngineError(
            "elk placer requires Node.js; install Node ≥18 and re-run "
            "'cd tools/elk-bridge && npm install'"
        )
    bridge = _bridge_path()
    if not (bridge / "node_modules" / "elkjs").is_dir():
        raise PlacerEngineError(
            f"elk-bridge dependencies not installed; run 'cd {bridge} && npm install'"
        )
    try:
        proc = subprocess.run(
            ["node", str(bridge / "elk-layout.mjs")],
            input=json.dumps(graph),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as e:
        raise PlacerEngineError(f"elk-bridge timed out after {e.timeout}s") from e
    if proc.returncode != 0:
        raise PlacerEngineError(
            f"elk-bridge failed (exit {proc.returncode}): {proc.stderr.strip()} "
            f"(stdout head: {proc.stdout[:200]!r})"
        )
    try:
        result: dict[str, Any] = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise PlacerEngineError(f"elk-bridge produced invalid JSON: {e}") from e
    return result


class ElkPlacer(Placer):
    """Layered Sugiyama-style placement via Eclipse Layout Kernel."""

    name = "elk"

    def place(
        self,
        schematic: Schematic,
        hints: dict[str, Any] | None = None,
    ) -> Schematic:
        validate(schematic)
        graph = _ir_to_elk_graph(schematic)

        if hints and "direction" in hints:
            direction = {
                "LR": "RIGHT",
                "RL": "LEFT",
                "TB": "DOWN",
                "BT": "UP",
            }.get(hints["direction"], "RIGHT")
            graph.setdefault("layoutOptions", {})["elk.direction"] = direction

        elk_result = _run_bridge(graph)
        return _elk_to_placed_schematic(schematic, elk_result)
