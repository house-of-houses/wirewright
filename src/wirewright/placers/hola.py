"""HOLA (Human-like Orthogonal Layout) placer adapter.

Uses the ``hola_graph`` Python package (https://github.com/shakfu/hola-graph,
the renamed ``pyhola``). HOLA does not have port constraints; we build one
node per Component, one edge per non-power/ground net pair, run layout,
then synthesize wires by routing pairwise between pin absolute positions
via :func:`wirewright.routing.orthogonal.l_shape`.

Power and ground nets are emitted as global rails (FLAGs at every connecting
pin), not HOLA edges.

The actual HOLA layout call runs in a subprocess (see
``_hola_subprocess.py``) so HOLA's C++ asserts (which abort the process)
don't kill the parent — they surface as :class:`PlacerEngineError`.

Reference:
    Kieffer, Dwyer, Marriott, Wybrow.
    "HOLA: Human-like Orthogonal Network Layout."
    IEEE TVCG 22(1), 2016.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from typing import Any

from wirewright.ir.model import Flag, Schematic, Wire
from wirewright.ir.validate import LTSPICE_GRID, validate, validate_placed
from wirewright.placers.base import Placer, PlacerEngineError, PlacerError
from wirewright.routing.orthogonal import l_shape, snap_to_grid
from wirewright.symbols.builtin import absolute_pin_position, symbol_geometry


def _stitching_edges(
    all_refs: list[str], existing_pairs: set[tuple[str, str]]
) -> list[tuple[str, str]]:
    """Compute virtual edges that stitch disconnected components into one graph.

    HOLA's stress-majorization aborts on disconnected input. Returns a list of
    extra ``(a, b)`` edges that, added to the connectivity, produce a single
    connected component. Components with no edges (isolated nodes) are chained
    in along with the rest.
    """
    from collections import defaultdict

    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in existing_pairs:
        adj[a].add(b)
        adj[b].add(a)

    visited: set[str] = set()
    components: list[list[str]] = []
    for ref in all_refs:
        if ref in visited:
            continue
        stack = [ref]
        comp: list[str] = []
        while stack:
            n = stack.pop()
            if n in visited:
                continue
            visited.add(n)
            comp.append(n)
            stack.extend(adj[n])
        components.append(comp)

    return [(components[i - 1][0], components[i][0]) for i in range(1, len(components))]


def _run_hola_subprocess(
    nodes: list[dict[str, Any]], edges: list[tuple[str, str]]
) -> dict[str, dict[str, float]]:
    """Run the HOLA subprocess; raise ``PlacerEngineError`` on abort or error."""
    payload = json.dumps({"nodes": nodes, "edges": [list(e) for e in edges]})
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "wirewright.placers._hola_subprocess"],
            input=payload,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as e:
        raise PlacerEngineError(f"hola subprocess timed out after {e.timeout}s") from e
    if proc.returncode != 0:
        # Negative returncode = signal (e.g., -6 = SIGABRT from C++ assertion).
        signal_hint = (
            f"signal {-proc.returncode}" if proc.returncode < 0 else f"exit {proc.returncode}"
        )
        stderr_tail = proc.stderr.strip().splitlines()[-3:]
        raise PlacerEngineError(
            f"hola subprocess failed ({signal_hint}); HOLA cannot lay out this graph. "
            f"Try --placer naive as a fallback. stderr: {' | '.join(stderr_tail)}"
        )
    try:
        result: dict[str, dict[str, float]] = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise PlacerEngineError(f"hola subprocess produced invalid JSON: {e}") from e
    return result


class HolaPlacer(Placer):
    """Stress-majorization placement via the HOLA algorithm (hola-graph)."""

    name = "hola"

    def place(
        self,
        schematic: Schematic,
        hints: dict[str, Any] | None = None,
    ) -> Schematic:
        try:
            import hola_graph  # noqa: F401
        except ImportError as e:
            raise PlacerEngineError(
                "hola placer requires hola-graph; install with "
                "'uv sync --extra hola' or 'uv add hola-graph'"
            ) from e

        validate(schematic)
        out = copy.deepcopy(schematic)

        power_or_ground: set[str] = {n.name for n in out.nets if n.is_power or n.is_ground}

        # Build the request payload for the subprocess.
        nodes: list[dict[str, Any]] = []
        for c in out.components:
            try:
                geo = symbol_geometry(c.symbol)
            except KeyError as e:
                raise PlacerError(f"Component {c.ref!r}: unknown symbol {c.symbol!r}") from e
            x_min, y_min, x_max, y_max = geo.bbox
            width = max(x_max - x_min, LTSPICE_GRID)
            height = max(y_max - y_min, LTSPICE_GRID)
            nodes.append({"label": c.ref, "width": float(width), "height": float(height)})

        # Pairwise edges per non-power/ground net (deduplicated by component pair).
        net_to_refs: dict[str, list[str]] = {}
        for c in out.components:
            for _pin_name, net_name in c.pins.items():
                if net_name in power_or_ground:
                    continue
                net_to_refs.setdefault(net_name, []).append(c.ref)

        edges: list[tuple[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for refs in net_to_refs.values():
            anchor = refs[0]
            for target in refs[1:]:
                if anchor == target:
                    continue
                pair = (anchor, target) if anchor < target else (target, anchor)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                edges.append((anchor, target))

        # HOLA aborts on disconnected graphs. Compute virtual edges between
        # disconnected components and append them.
        edges.extend(_stitching_edges([c.ref for c in out.components], seen_pairs))

        # Run the layout in a subprocess so HOLA's C++ asserts in faces.cpp
        # (and similar) don't kill the parent. The subprocess returns either
        # a layout result on stdout or a non-zero exit (signal-coded for
        # SIGABRT on assertion failure).
        layout = _run_hola_subprocess(nodes, edges)

        for c in out.components:
            node_layout = layout.get(c.ref)
            if node_layout is None:
                raise PlacerEngineError(f"hola subprocess did not place {c.ref!r}")
            geo = symbol_geometry(c.symbol)
            sx, sy = snap_to_grid(
                (
                    round(node_layout["left"]) - geo.bbox[0],
                    round(node_layout["top"]) - geo.bbox[1],
                )
            )
            c.x, c.y = sx, sy
            c.orientation = "R0"

        # Synthesize wires by routing pairwise between pin absolute positions.
        # Skip self-loops (multiple pins of same net on same component).
        out.wires = []
        for net_name in net_to_refs:
            pin_positions: list[tuple[int, int]] = []
            for c in out.components:
                for pin_name, pn in c.pins.items():
                    if pn == net_name:
                        assert c.x is not None and c.y is not None
                        pin_positions.append(
                            absolute_pin_position((c.x, c.y), c.symbol, pin_name, c.orientation)
                        )
            if len({p for p in pin_positions}) < 2:
                continue
            wire_anchor = pin_positions[0]
            for wire_target in pin_positions[1:]:
                if wire_target == wire_anchor:
                    continue
                out.wires.extend(l_shape(wire_anchor, wire_target))

        # Power/ground rails as flags + stub wires.
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

        out.wires = [w for w in out.wires if (w.x1, w.y1) != (w.x2, w.y2)]

        validate_placed(out)
        return out
