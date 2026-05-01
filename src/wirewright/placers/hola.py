"""HOLA (Human-like Orthogonal Layout) placer adapter.

Uses the ``hola_graph`` Python package (https://github.com/shakfu/hola-graph,
the renamed ``pyhola``). HOLA does not have port constraints; we build one
node per Component, one edge per non-power/ground net pair, run layout,
then synthesize wires by routing pairwise between pin absolute positions
via :func:`wirewright.routing.orthogonal.l_shape`.

Power and ground nets are emitted as global rails (FLAGs at every connecting
pin), not HOLA edges.

Reference:
    Kieffer, Dwyer, Marriott, Wybrow.
    "HOLA: Human-like Orthogonal Network Layout."
    IEEE TVCG 22(1), 2016.
"""

from __future__ import annotations

import copy
from typing import Any

from wirewright.ir.model import Flag, Schematic, Wire
from wirewright.ir.validate import LTSPICE_GRID, validate, validate_placed
from wirewright.placers.base import Placer, PlacerEngineError, PlacerError
from wirewright.routing.orthogonal import l_shape, snap_to_grid
from wirewright.symbols.builtin import absolute_pin_position, symbol_geometry


def _stitch_disconnected_components(
    g: Any, all_refs: list[str], existing_pairs: set[tuple[str, str]]
) -> None:
    """Add virtual edges between disconnected components so HOLA gets a connected graph.

    HOLA's stress-majorization aborts on disconnected input. We compute the
    connected components implied by ``existing_pairs`` and add one virtual edge
    per pair of components to chain them together. Components with no edges
    (isolated nodes) are also chained in.
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

    # Chain one representative from each component to the previous one.
    for i in range(1, len(components)):
        a, b = components[i - 1][0], components[i][0]
        g.connect(a, b)


def _is_planar(all_refs: list[str], pairs: set[tuple[str, str]]) -> bool:
    """Quick planarity check via NetworkX. HOLA requires planar input."""
    import networkx as nx  # type: ignore[import-untyped]

    graph = nx.Graph()
    graph.add_nodes_from(all_refs)
    for a, b in pairs:
        graph.add_edge(a, b)
    is_planar, _ = nx.check_planarity(graph)
    return bool(is_planar)


class HolaPlacer(Placer):
    """Stress-majorization placement via the HOLA algorithm (hola-graph)."""

    name = "hola"

    def place(
        self,
        schematic: Schematic,
        hints: dict[str, Any] | None = None,
    ) -> Schematic:
        try:
            from hola_graph import HolaGraph
        except ImportError as e:
            raise PlacerEngineError(
                "hola placer requires hola-graph; install with "
                "'uv sync --extra hola' or 'uv add hola-graph'"
            ) from e

        validate(schematic)
        out = copy.deepcopy(schematic)

        power_or_ground: set[str] = {n.name for n in out.nets if n.is_power or n.is_ground}

        g = HolaGraph()
        for c in out.components:
            try:
                geo = symbol_geometry(c.symbol)
            except KeyError as e:
                raise PlacerError(f"Component {c.ref!r}: unknown symbol {c.symbol!r}") from e
            x_min, y_min, x_max, y_max = geo.bbox
            width = max(x_max - x_min, LTSPICE_GRID)
            height = max(y_max - y_min, LTSPICE_GRID)
            g.add_node(width=float(width), height=float(height), label=c.ref)

        # Pairwise edges per non-power/ground net (deduplicated by component pair).
        net_to_refs: dict[str, list[str]] = {}
        for c in out.components:
            for _pin_name, net_name in c.pins.items():
                if net_name in power_or_ground:
                    continue
                net_to_refs.setdefault(net_name, []).append(c.ref)

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
                g.connect(anchor, target)

        # HOLA aborts on disconnected graphs. Stitch together connected
        # components with virtual edges so the input is always a single
        # connected graph; the virtual edges don't affect emitted wires.
        _stitch_disconnected_components(g, [c.ref for c in out.components], seen_pairs)

        # HOLA's C++ asserts in faces.cpp::identifyExternalFace on certain
        # graph structures we cannot fully predict from Python. We screen for
        # non-planar graphs (definite abort cause); other crashes require
        # subprocess isolation, deferred to v0.2.
        graph_refs = [c.ref for c in out.components]
        if not _is_planar(graph_refs, seen_pairs):
            raise PlacerEngineError(
                "hola placer cannot handle non-planar graphs; "
                "try --placer elk instead. (HOLA limitation.)"
            )

        g.layout()

        # HOLA's node.x / node.y is the geometric CENTER; node.bounds is
        # (left, top, right, bottom) in canvas coords. Component origin
        # (LTspice SYMBOL position) = bbox-canvas-top-left minus bbox-symbol x_min.
        for c in out.components:
            node = g.node(c.ref)
            geo = symbol_geometry(c.symbol)
            left, top, _right, _bottom = node.bounds
            sx, sy = snap_to_grid((round(left) - geo.bbox[0], round(top) - geo.bbox[1]))
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
