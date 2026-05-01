# Phase 3 Implementation Plan (rev 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first real placer. `wirewright render <fixture> --placer elk` produces a valid `.asc` for the three canonical fixtures (`divider.net`, `tb303-envelope.net`, `tb303-vco-integrated.net`), satisfying the Phase 3 DoD per `docs/PLAN.md`.

**Architecture:** Six tasks. (1) Install `elkjs`, smoke-test the bridge with a port-side-bearing graph to verify ELK's property-name accepts `port.side` shorthand or requires `org.eclipse.elk.port.side`. (2) Replace the existing stub `routing/orthogonal.py` with extracted snap-and-route helpers from `placers/grid_naive.py`. (3) IR → ELK JSON conversion using **`FIXED_POS` port constraint** with explicit per-port `x`/`y` (relative to node top-left = bbox top-left). Single ELK hyper-edge per non-power/ground net (multiple `sources` and `targets`), not pairwise. ELK `spacing.nodeNode` set to a multiple of `LTSPICE_GRID` (64) so post-snap doesn't produce overlap. (4) ELK output → IR: extract per-node `(x, y)`, translate via `sx = node.x - bbox[0], sy = node.y - bbox[1]`, snap to grid; rebuild wires from `edge.sections` via `manhattan_segments`. Power/ground emit as FLAGs. Subprocess wrapping converts `TimeoutExpired` to `PlacerEngineError`. (5) End-to-end integration test against real Node bridge (skipped if unavailable) plus CI Node-setup so the test runs there too. (6) Render canonical fixtures with round-trip verification (re-parse the emitted `.asc` and assert connectivity isomorphism), finalize spec, bump tracker.

**Tech Stack:** Python 3.11, pytest, ruff, mypy, uv, Node.js ≥18, `elkjs ^0.9.3`. The Node.js bridge is a runtime dependency of the `elk` placer only; users opting for `naive` need no Node install.

**Spec sources:**
- `docs/PLAN.md` Phase 3 (DoD: render all three fixtures via `--placer elk`; finalize `placer-interface.md` based on real implementation experience).
- `docs/specs/placer-interface.md` (currently draft; finalize at the end of this phase).
- `docs/specs/ir.md` (no changes).
- `docs/specs/asc-emitter.md` (no changes).
- `docs/adr/0003-placer-adapter-pattern.md` (the architectural decision; cross-check).
- `docs/adr/0004-elk-and-hola-as-baselines.md` (DoD shape).

**Out of scope (deferred):**
- Pinned components via `hints["pinned"]`. Spec mentions; v0.3+.
- Aspect-ratio control via `hints["aspect_ratio"]`. v0.3+.
- Hierarchical schematics. Subcircuits already flattened by Phase 2 parser.
- Edge labels, wire-label positioning, visual style tweaks.
- LED/Zener/Schottky symbol variants. Phase 2 already maps every D to `diode`.

---

## File Structure

| Path | Action | Responsibility |
|------|--------|----------------|
| `tools/elk-bridge/package.json` | Existing — keep | elkjs dependency declaration. |
| `tools/elk-bridge/node_modules/` | New (npm install) | Local elkjs install. Gitignored. |
| `tools/elk-bridge/elk-layout.mjs` | Existing — minor verify | Already complete; verify it runs. |
| `src/wirewright/placers/elk.py` | Rewrite | Implement `ElkPlacer.place()`: IR→ELK JSON, subprocess, ELK JSON→IR. |
| `src/wirewright/routing/orthogonal.py` | Replace stub | Extract L-shape snap-and-route helpers from `grid_naive.py`. (File exists as a `NotImplementedError` stub from Phase 0.) |
| `src/wirewright/placers/grid_naive.py` | Modify | Use `routing/orthogonal.py` helpers; behavior unchanged. |
| `tests/unit/test_elk.py` | Create | Tests for IR↔ELK JSON conversion using synthetic graphs (no real Node subprocess; the conversion logic is pure). |
| `tests/unit/test_routing.py` | Create | Tests for `routing/orthogonal.py` helpers. |
| `tests/integration/test_elk_e2e.py` | Create | One end-to-end test using the real Node bridge against a 2-resistor synthetic schematic; skip if `node` not on PATH. |
| `.gitignore` | Modify | Ignore `tools/elk-bridge/node_modules/`. |
| `.github/workflows/ci.yml` | Modify | Add `actions/setup-node@v4` + `npm install` so e2e test runs in CI. |
| `docs/specs/placer-interface.md` | Modify | Status: draft → stable in v0.1; document hint dialect, ELK-specific failure modes. |
| `docs/PLAN.md` | Modify | Phase 3 status: complete in v0.1. |
| `CLAUDE.md` | Modify | Phase tracker: 2 → 3 complete. |

---

## Task 1: npm install elkjs and verify the bridge

**Background.** `tools/elk-bridge/package.json` declares `elkjs ^0.9.3`. `elk-layout.mjs` reads stdin JSON, runs ELK layout, writes stdout JSON. Verifying the bridge is a one-line `npm install`, then a smoke test.

**Files:**
- Modify: `.gitignore`
- Run: `npm install` in `tools/elk-bridge/`

- [ ] **Step 1.1: Install elkjs**

```bash
cd tools/elk-bridge && npm install
ls -d node_modules/elkjs
```

Expected: `node_modules/elkjs` exists.

- [ ] **Step 1.2: Add `tools/elk-bridge/node_modules/` to `.gitignore`**

Append to `.gitignore`:

```
# Node.js dependencies for the ELK bridge
tools/elk-bridge/node_modules/
tools/elk-bridge/package-lock.json
```

- [ ] **Step 1.3: Smoke test the bridge with FIXED_POS ports**

```bash
cd tools/elk-bridge && echo '{
  "id":"root",
  "layoutOptions":{"elk.algorithm":"layered","elk.portConstraints":"FIXED_POS"},
  "children":[
    {"id":"n1","width":32,"height":80,
     "ports":[{"id":"n1.A","x":16,"y":0,"properties":{"port.side":"NORTH"}},
              {"id":"n1.B","x":16,"y":80,"properties":{"port.side":"SOUTH"}}]},
    {"id":"n2","width":32,"height":80,
     "ports":[{"id":"n2.A","x":16,"y":0,"properties":{"port.side":"NORTH"}}]}
  ],
  "edges":[{"id":"e1","sources":["n1.B"],"targets":["n2.A"]}]
}' | node elk-layout.mjs
```

Expected: stdout JSON with each child having `x`/`y` populated and ports also having absolute positions echoed back. Verify the property name `port.side` works as a short form (ELK accepts both `port.side` and `org.eclipse.elk.port.side`); if it doesn't, switch to the long form throughout the plan.

- [ ] **Step 1.4: Commit**

```bash
git add .gitignore
git commit -m "chore(elk-bridge): npm install elkjs; gitignore node_modules"
```

---

## Task 2: Extract `routing/orthogonal.py` from `grid_naive.py`

**Background.** `placers/grid_naive.py` has `_l_shape` and `_snap` helpers that convert a pair of canvas points into axis-aligned `Wire`s with grid-snapped endpoints. These are not naive-specific; ELK and HOLA need the same primitives. Move them to `src/wirewright/routing/orthogonal.py`. Behavior unchanged.

**Files:**
- Create: `src/wirewright/routing/orthogonal.py`
- Modify: `src/wirewright/placers/grid_naive.py`
- Create: `tests/unit/test_routing.py`

- [ ] **Step 2.1: Implement `routing/orthogonal.py`**

```python
"""Axis-aligned wire routing primitives.

Pure helpers shared by every placer. No placement logic; the placer decides
where pins are, this module decides how to draw the wire between them.
"""

from __future__ import annotations

from wirewright.ir.model import Wire
from wirewright.ir.validate import LTSPICE_GRID


def snap_to_grid(point: tuple[int, int]) -> tuple[int, int]:
    """Round a (x, y) to the LTspice grid."""
    return (
        round(point[0] / LTSPICE_GRID) * LTSPICE_GRID,
        round(point[1] / LTSPICE_GRID) * LTSPICE_GRID,
    )


def l_shape(a: tuple[int, int], b: tuple[int, int]) -> list[Wire]:
    """Two axis-aligned wire segments connecting ``a`` to ``b`` through an L bend.

    Snaps endpoints to the LTspice grid. The bend is horizontal-first.
    Returns a single-segment list when ``a`` and ``b`` are colinear on x or y.
    """
    ax, ay = snap_to_grid(a)
    bx, by = snap_to_grid(b)
    if ax == bx or ay == by:
        return [Wire(ax, ay, bx, by)]
    return [
        Wire(ax, ay, bx, ay),
        Wire(bx, ay, bx, by),
    ]


def manhattan_segments(points: list[tuple[int, int]]) -> list[Wire]:
    """Connect a sequence of points pairwise with axis-aligned wires.

    Each consecutive pair is rendered as ``l_shape``. Useful for ELK edge
    sections that consist of a list of bend points.
    """
    wires: list[Wire] = []
    for i in range(len(points) - 1):
        wires.extend(l_shape(points[i], points[i + 1]))
    return wires
```

- [ ] **Step 2.2: Tests**

Create `tests/unit/test_routing.py`:

```python
"""Tests for routing/orthogonal.py."""

from __future__ import annotations

import pytest

from wirewright.routing.orthogonal import l_shape, manhattan_segments, snap_to_grid


def test_snap_rounds_to_grid() -> None:
    assert snap_to_grid((17, 0)) == (16, 0)
    assert snap_to_grid((24, 24)) == (32, 32)
    assert snap_to_grid((-9, 7)) == (-16, 0)


def test_l_shape_colinear_x() -> None:
    wires = l_shape((80, 64), (80, 160))
    assert len(wires) == 1
    assert (wires[0].x1, wires[0].y1, wires[0].x2, wires[0].y2) == (80, 64, 80, 160)


def test_l_shape_colinear_y() -> None:
    wires = l_shape((80, 64), (272, 64))
    assert len(wires) == 1


def test_l_shape_bends() -> None:
    wires = l_shape((80, 80), (272, 160))
    assert len(wires) == 2
    # Horizontal first.
    assert (wires[0].y1, wires[0].y2) == (80, 80)
    assert (wires[1].x1, wires[1].x2) == (272, 272)


def test_manhattan_chain() -> None:
    pts = [(0, 0), (32, 0), (32, 64)]
    wires = manhattan_segments(pts)
    # First segment is colinear (1 wire); second segment is colinear (1 wire).
    assert len(wires) == 2
```

- [ ] **Step 2.3: Refactor `grid_naive.py` to use the helpers**

Replace `_l_shape` and `_snap` in `placers/grid_naive.py` with imports from `routing/orthogonal`. Existing behavior preserved.

```python
from wirewright.routing.orthogonal import l_shape

# delete the local _l_shape and _snap; replace call sites:
# out.wires.extend(_l_shape(anchor, (px, py)))
# →
# out.wires.extend(l_shape(anchor, (px, py)))
```

- [ ] **Step 2.4: Run tests, lint, format, types, commit**

```bash
uv run pytest tests/unit/test_routing.py tests/unit/test_placers.py -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add src/wirewright/routing/orthogonal.py src/wirewright/placers/grid_naive.py tests/unit/test_routing.py
git commit -m "refactor(routing): extract orthogonal routing primitives from grid_naive"
```

---

## Task 3: IR → ELK JSON conversion

**Background.** ELK's JSON graph format needs:
- `id`: top-level graph id (use `"root"`).
- `children`: list of nodes, each with `id`, `width`, `height`, `ports[]`, optional `x`/`y`.
- `edges`: list of edges, each with `id`, `sources` (list of port ids), `targets` (list of port ids).
- `layoutOptions`: per-graph or per-node ELK config.

For each `Component` in the IR, emit one node with `id = ref`, `width = bbox_width`, `height = bbox_height`, and one port per pin. Port `id` = `f"{ref}.{pin_name}"`. Port `properties.port.side` = `WEST`/`EAST`/`NORTH`/`SOUTH` derived from the pin's offset relative to the symbol bbox center.

For each non-power/ground `Net` with ≥2 connections, emit one edge per pair (or one hyper-edge with multiple sources/targets — ELK supports it). For v0.1 emit pairwise edges (simpler; ELK handles them).

**Files:**
- Modify: `src/wirewright/placers/elk.py`
- Create: `tests/unit/test_elk.py`

- [ ] **Step 3.1: Implement `_ir_to_elk_graph` (pure function)**

In `src/wirewright/placers/elk.py`, replace the stub with:

```python
"""ELK (Eclipse Layout Kernel) placer adapter.

Converts IR Schematic to ELK JSON graph, runs the Node.js bridge in
``tools/elk-bridge/``, parses the result back, snaps to the LTspice grid,
and returns a placed Schematic.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from wirewright.ir.model import Component, Flag, Schematic, Wire
from wirewright.ir.validate import LTSPICE_GRID, validate, validate_placed
from wirewright.placers.base import Placer, PlacerEngineError, PlacerError
from wirewright.routing.orthogonal import manhattan_segments, snap_to_grid
from wirewright.symbols.builtin import absolute_pin_position, symbol_geometry


def _bridge_path() -> Path:
    """Resolve the elk-bridge directory relative to this package."""
    return Path(__file__).resolve().parent.parent.parent.parent / "tools/elk-bridge"


_SIDE_NAMES = {"W": "WEST", "E": "EAST", "N": "NORTH", "S": "SOUTH"}


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

    Uses FIXED_POS port constraint so ELK honors our explicit per-port (x, y)
    relative to each node's top-left = bbox top-left. Ground/power nets are
    omitted from edges (they get global rails after layout). Multi-pin nets
    use a single hyper-edge per net.
    """
    children: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    power_or_ground: set[str] = {
        n.name for n in schematic.nets if n.is_power or n.is_ground
    }

    for c in schematic.components:
        try:
            geo = symbol_geometry(c.symbol)
        except KeyError as e:
            raise PlacerError(
                f"Component {c.ref!r}: unknown symbol {c.symbol!r}"
            ) from e
        x_min, y_min, x_max, y_max = geo.bbox
        width = max(x_max - x_min, LTSPICE_GRID)
        height = max(y_max - y_min, LTSPICE_GRID)
        ports = []
        for pin_name in c.pins:
            pin_x, pin_y = geo.pins[pin_name]
            ports.append({
                "id": f"{c.ref}.{pin_name}",
                "x": pin_x - x_min,
                "y": pin_y - y_min,
                "properties": {"port.side": _port_side(c.symbol, pin_name)},
            })
        children.append({
            "id": c.ref,
            "width": width,
            "height": height,
            "ports": ports,
            "properties": {"portConstraints": "FIXED_POS"},
        })

    # Hyper-edges: one ELK edge per non-power/ground net with ≥2 connections.
    net_to_ports: dict[str, list[str]] = {}
    for c in schematic.components:
        for pin_name, net_name in c.pins.items():
            if net_name in power_or_ground:
                continue
            net_to_ports.setdefault(net_name, []).append(f"{c.ref}.{pin_name}")

    edge_id = 0
    for net_name, ports in net_to_ports.items():
        if len(ports) < 2:
            continue
        edges.append({
            "id": f"e{edge_id}_{net_name}",
            "sources": [ports[0]],
            "targets": ports[1:],
        })
        edge_id += 1

    # Grid-aligned spacing so post-snap cannot produce overlap.
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
```

- [ ] **Step 3.2: Tests for `_ir_to_elk_graph`**

Create `tests/unit/test_elk.py`:

```python
"""Tests for the ELK placer's pure IR↔ELK JSON conversion."""

from __future__ import annotations

import pytest

from wirewright.ir.model import Component, Net, Schematic
from wirewright.placers.elk import _ir_to_elk_graph, _port_side


def _two_resistor() -> Schematic:
    return Schematic(
        components=[
            Component(ref="R1", symbol="res", pins={"1": "a", "2": "b"}),
            Component(ref="R2", symbol="res", pins={"1": "b", "2": "0"}),
        ],
        nets=[Net("a"), Net("b"), Net("0", is_ground=True)],
    )


def test_ir_to_elk_emits_one_node_per_component() -> None:
    graph = _ir_to_elk_graph(_two_resistor())
    assert {n["id"] for n in graph["children"]} == {"R1", "R2"}


def test_ir_to_elk_emits_one_port_per_pin() -> None:
    graph = _ir_to_elk_graph(_two_resistor())
    r1_ports = {p["id"] for p in graph["children"][0]["ports"]}
    assert r1_ports == {"R1.1", "R1.2"}


def test_ir_to_elk_omits_power_ground_edges() -> None:
    """Net '0' is ground; no edges should reference it."""
    graph = _ir_to_elk_graph(_two_resistor())
    edge_endpoints = {p for e in graph["edges"] for p in e["sources"] + e["targets"]}
    # R2.pin2 = "0" should NOT appear in any edge.
    assert "R2.2" not in edge_endpoints


def test_ir_to_elk_emits_hyperedge_per_net() -> None:
    graph = _ir_to_elk_graph(_two_resistor())
    # Net "b" connects R1.2 and R2.1 → 1 hyper-edge. Net "a" has only R1.1
    # → no edge (single-port nets are skipped).
    assert len(graph["edges"]) == 1
    e = graph["edges"][0]
    assert e["sources"] == ["R1.2"]
    assert e["targets"] == ["R2.1"]


def test_ir_to_elk_uses_fixed_pos_with_explicit_port_xy() -> None:
    graph = _ir_to_elk_graph(_two_resistor())
    r1 = next(c for c in graph["children"] if c["id"] == "R1")
    assert r1["properties"]["portConstraints"] == "FIXED_POS"
    # res bbox (0, 16, 32, 96); pin 1 (16, 16) → port (16-0, 16-16) = (16, 0).
    p1 = next(p for p in r1["ports"] if p["id"] == "R1.1")
    assert (p1["x"], p1["y"]) == (16, 0)


def test_ir_to_elk_grid_aligned_spacing() -> None:
    graph = _ir_to_elk_graph(_two_resistor())
    spacing = int(graph["layoutOptions"]["elk.spacing.nodeNode"])
    assert spacing % 16 == 0


def test_port_side_for_resistor_pins() -> None:
    # res pins (16, 16) and (16, 96) in bbox (0, 16, 32, 96).
    # Pin 1 is at top edge (py == y_min = 16); closest-edge → NORTH.
    # Pin 2 is at bottom edge (py == y_max = 96); closest-edge → SOUTH.
    assert _port_side("res", "1") == "NORTH"
    assert _port_side("res", "2") == "SOUTH"


def test_port_side_for_mosfet_gate() -> None:
    # nmos gate at (0, 80) in bbox (0, 0, 48, 96).
    # px == x_min → distance to W is 0 (smallest) → WEST.
    assert _port_side("nmos", "G") == "WEST"


def test_port_side_for_bjt_base() -> None:
    # npn base at (0, 48) in bbox (0, 0, 64, 96). Closest edge: WEST.
    assert _port_side("npn", "B") == "WEST"


def test_port_side_for_opamp_out() -> None:
    # opamp2 OUT at (32, 64) in bbox (-32, 32, 32, 96). Closest edge: EAST.
    assert _port_side("opamp2", "OUT") == "EAST"


def test_unknown_symbol_raises_placer_error() -> None:
    from wirewright.placers.base import PlacerError

    s = Schematic(
        components=[Component(ref="X1", symbol="not_real", pins={"a": "n1"})],
        nets=[Net("n1")],
    )
    with pytest.raises(PlacerError, match="unknown symbol"):
        _ir_to_elk_graph(s)
```

- [ ] **Step 3.3: Run, commit (no integration yet)**

```bash
uv run pytest tests/unit/test_elk.py -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add src/wirewright/placers/elk.py tests/unit/test_elk.py
git commit -m "feat(elk): IR → ELK JSON conversion (pure helpers, no subprocess)"
```

---

## Task 4: ELK JSON → IR conversion + subprocess wiring

**Background.** ELK output contains:
- Each `child` has `x`/`y` (top-left of node bounding box) and per-port positions.
- Each `edge` has `sections[]`, each section has `startPoint`, `endPoint`, optional `bendPoints[]`.

Convert back: place each component at `(x + bbox_offset_x, y + bbox_offset_y)` snapped to grid (component's IR origin needs to coincide with the symbol's pin offsets — the bbox offset adjusts for the symbol library's reference point). Set orientation = `R0` for v0.1 (ELK doesn't rotate; rotation requires hint support deferred to v0.3+).

For wires: walk each edge's sections, build a list of bend points (`startPoint`, then any `bendPoints`, then `endPoint`), and convert pairwise via `routing/orthogonal.manhattan_segments`.

For ground/power nets: emit `Flag(net="0")` at every pin connected to a ground net; emit `Flag(net=net_name)` at every pin connected to a power net.

**Files:**
- Modify: `src/wirewright/placers/elk.py`
- Modify: `tests/unit/test_elk.py`

- [ ] **Step 4.1: Implement `_elk_to_placed_schematic`**

```python
def _elk_to_placed_schematic(
    schematic: Schematic, elk_result: dict[str, Any]
) -> Schematic:
    """Apply ELK output to a copy of the input schematic."""
    import copy

    out = copy.deepcopy(schematic)
    placed_by_id: dict[str, dict[str, Any]] = {n["id"]: n for n in elk_result.get("children", [])}

    for c in out.components:
        node = placed_by_id.get(c.ref)
        if node is None:
            raise PlacerEngineError(f"ELK did not place component {c.ref!r}")
        # ELK gives node origin at the bbox top-left. Symbol origin in IR is
        # offset by bbox[0]/bbox[1].
        geo = symbol_geometry(c.symbol)
        sx, sy = snap_to_grid(
            (int(node.get("x", 0)) - geo.bbox[0], int(node.get("y", 0)) - geo.bbox[1])
        )
        c.x, c.y = sx, sy
        c.orientation = "R0"

    # Wires from ELK edge sections (snap each bend point to grid).
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

    # Power/ground rails as flags.
    out.flags = []
    for c in out.components:
        for pin_name, net_name in c.pins.items():
            net = next((n for n in out.nets if n.name == net_name), None)
            if net is None:
                continue
            if net.is_ground or net.name == "0":
                pos = absolute_pin_position(
                    (c.x or 0, c.y or 0), c.symbol, pin_name, c.orientation
                )
                # Stub wire down + flag.
                stub_y = pos[1] + LTSPICE_GRID * 2
                out.wires.append(Wire(pos[0], pos[1], pos[0], stub_y))
                out.flags.append(Flag(pos[0], stub_y, "0"))
            elif net.is_power:
                pos = absolute_pin_position(
                    (c.x or 0, c.y or 0), c.symbol, pin_name, c.orientation
                )
                out.flags.append(Flag(pos[0], pos[1], net.name))

    validate_placed(out)
    return out


def _strip_zero_length_wires(wires: list[Wire]) -> list[Wire]:
    """Drop wires whose endpoints are identical after grid snapping."""
    return [w for w in wires if (w.x1, w.y1) != (w.x2, w.y2)]
```

- [ ] **Step 4.2: Implement `ElkPlacer.place` to wire it all together**

```python
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

        layout_options: dict[str, Any] = {}
        if hints and "direction" in hints:
            layout_options["elk.direction"] = {
                "LR": "RIGHT", "RL": "LEFT", "TB": "DOWN", "BT": "UP"
            }.get(hints["direction"], "RIGHT")
        if layout_options:
            graph["layoutOptions"] = layout_options

        elk_result = _run_bridge(graph)
        return _elk_to_placed_schematic(schematic, elk_result)


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
            f"elk-bridge dependencies not installed; run "
            f"'cd {bridge} && npm install'"
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
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise PlacerEngineError(f"elk-bridge produced invalid JSON: {e}") from e
```

- [ ] **Step 4.3: Test elk_to_placed_schematic with a synthetic ELK result**

Append to `tests/unit/test_elk.py`:

```python
def test_elk_to_placed_applies_coordinates(monkeypatch: pytest.MonkeyPatch) -> None:
    from wirewright.placers.elk import _elk_to_placed_schematic

    sch = _two_resistor()
    elk_result = {
        "children": [
            {"id": "R1", "x": 64, "y": 64},
            {"id": "R2", "x": 256, "y": 64},
        ],
        "edges": [
            {
                "id": "e0",
                "sections": [
                    {
                        "startPoint": {"x": 80, "y": 160},
                        "endPoint": {"x": 272, "y": 80},
                        "bendPoints": [{"x": 272, "y": 160}],
                    }
                ],
            }
        ],
    }
    placed = _elk_to_placed_schematic(sch, elk_result)
    r1 = placed.component_by_ref("R1")
    assert (r1.x, r1.y, r1.orientation) == (64, 64, "R0")
    assert len(placed.wires) >= 1
    # Ground flag for net "0" at R2.pin2.
    assert any(f.net == "0" for f in placed.flags)
```

- [ ] **Step 4.4: Run, commit**

```bash
uv run pytest tests/unit/test_elk.py -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add src/wirewright/placers/elk.py tests/unit/test_elk.py
git commit -m "feat(elk): ELK JSON → IR conversion + subprocess wiring"
```

---

## Task 5: End-to-end integration test + CI Node setup

**Background.** A single integration test that uses the real subprocess. Skipped if `node` not on PATH or `elk-bridge/node_modules` missing.

**Files:**
- Create: `tests/integration/test_elk_e2e.py`

- [ ] **Step 5.1: Integration test**

```python
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
    # Coordinates are grid-aligned.
    for c in placed.components:
        assert c.x is not None and c.x % 16 == 0
        assert c.y is not None and c.y % 16 == 0
```

- [ ] **Step 5.2: Add Node setup to CI**

In `.github/workflows/ci.yml`, add after the `astral-sh/setup-uv@v3` step:

```yaml
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install elk-bridge dependencies
        run: cd tools/elk-bridge && npm install
```

This makes the e2e test run on CI rather than silently skip.

- [ ] **Step 5.3: Run, commit**

```bash
uv run pytest tests/integration/test_elk_e2e.py -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add tests/integration/test_elk_e2e.py .github/workflows/ci.yml
git commit -m "test(elk): end-to-end placement test + CI Node setup"
```

---

## Task 6: Render canonical fixtures via CLI; finalize spec; bump tracker

**Background.** Phase 3 DoD: `wirewright render <fixture> -o <out.asc> --placer elk` works on all three canonical fixtures.

**Files:**
- Modify: `docs/specs/placer-interface.md`
- Modify: `docs/PLAN.md`
- Modify: `CLAUDE.md`

- [ ] **Step 6.1: Render canonical fixtures with round-trip verification**

For each canonical fixture, render via CLI, then re-parse the emitted `.asc`
and assert connectivity isomorphism with the input netlist. This catches the
"wires don't connect to pins" failure mode that ELK's port-side defaults
would otherwise produce.

```bash
for fix in tests/fixtures/easy/divider.net \
           tests/fixtures/medium/tb303-envelope.net \
           tests/fixtures/hard/tb303-vco-integrated.net; do
  test -f "$fix" || continue
  out=$(mktemp -t wwrender.XXXXXX.asc)
  uv run wirewright render "$fix" -o "$out" --placer elk
  echo "=== $fix → $out (size $(wc -c < $out))"
  test -s "$out"
done
```

Add a Python integration test (`tests/integration/test_elk_render.py`) that
does the same in-process plus the round-trip check:

```python
"""Render canonical fixtures via ELK and verify round-trip connectivity."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from wirewright.emit.asc import emit_asc
from wirewright.parse.ltspice_asc import parse_asc_text
from wirewright.parse.spice import parse_spice_file
from wirewright.placers.elk import ElkPlacer

_BRIDGE = Path(__file__).resolve().parents[2] / "tools/elk-bridge"


def _bridge_available() -> bool:
    return shutil.which("node") is not None and (_BRIDGE / "node_modules" / "elkjs").is_dir()


def _connectivity_signature(s):
    sig = {}
    for c in s.components:
        for pin_name, net_name in c.pins.items():
            sig.setdefault(net_name, set()).add((c.ref, pin_name))
    return {k: frozenset(v) for k, v in sig.items()}


@pytest.mark.skipif(not _bridge_available(), reason="elk-bridge not set up")
@pytest.mark.parametrize("fixture_relpath", [
    "easy/divider.net",
    "medium/tb303-envelope.net",
    "hard/tb303-vco-integrated.net",
])
def test_elk_renders_canonical_fixture_with_connectivity_preserved(
    fixture_relpath: str,
) -> None:
    fixture = Path(__file__).resolve().parents[2] / "tests/fixtures" / fixture_relpath
    if not fixture.exists():
        pytest.skip(f"fixture not present: {fixture_relpath}")

    parsed_input = parse_spice_file(fixture)
    placed = ElkPlacer().place(parsed_input)
    asc_text = emit_asc(placed)
    reparsed = parse_asc_text(asc_text)

    sig_in = _connectivity_signature(placed)
    sig_out = _connectivity_signature(reparsed)
    # Connectivity isomorphism: same multiset of (ref, pin) signatures.
    assert sorted(sig_in.values()) == sorted(sig_out.values()), (
        f"connectivity changed across emit/parse round-trip for {fixture_relpath}"
    )
```

- [ ] **Step 6.2: Mark placer-interface spec stable**

Edit `docs/specs/placer-interface.md`. Change "Status: draft" to "Status: stable in v0.1." Add an "ELK-specific" subsection under "Hints recognized by specific back ends":

```markdown
### ELK
- ``direction``: maps to ``elk.direction`` (LR→RIGHT, RL→LEFT, TB→DOWN, BT→UP). Default RIGHT.
- ``aspect_ratio``, ``pinned``: not yet supported in v0.1; ignored silently.
```

- [ ] **Step 6.3: Mark Phase 3 done in PLAN.md**

Add `**Status**: complete in v0.1.` after Phase 3's "Depends on: Phase 2." line.

- [ ] **Step 6.4: Bump phase tracker in CLAUDE.md**

```markdown
**Current phase**: 3 complete; Phase 4 (HOLA baseline) starting.
```

- [ ] **Step 6.5: Final smoke + commit**

```bash
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add tests/integration/test_elk_render.py docs/specs/placer-interface.md docs/PLAN.md CLAUDE.md
git commit -m "feat(elk): Phase 3 complete — render canonical fixtures via --placer elk"
```

---

## Self-Review

**Spec coverage:**
- ELK placer implementing the `Placer` contract: Tasks 3, 4. ✓
- Node bridge in `tools/elk-bridge/`: existing scaffold; Task 1 verifies. ✓
- Render all three fixtures via CLI: Task 6. ✓
- Power/ground as global rails (not edges): Tasks 3 (omitted from edges) and 4 (FLAG emission). ✓
- `routing/orthogonal.py` extracted: Task 2. ✓
- `placer-interface.md` finalized based on real implementation: Task 6.2. ✓

**Placeholder scan:** every step has concrete code or commands.

**Type consistency:**
- `_ir_to_elk_graph(s) → dict[str, Any]`: pure, used by Tasks 3/4.
- `_elk_to_placed_schematic(sch, elk_result) → Schematic`: Task 4.
- `_run_bridge(graph) → dict[str, Any]`: Task 4.
- ELK port id format `f"{ref}.{pin_name}"`: consistent across emit and parse paths.

**Risks worth flagging:**
- **Edge-section snap may produce wires that don't terminate exactly on pin coordinates.** v0.1 strips zero-length wires (Task 4's `_connect_wires_to_pins`); pin-snapping is conservative. If the canonical fixture renders open in LTspice but with disconnected wires, this is the place to investigate.
- **ELK orthogonal routing requires `portConstraints: FIXED_SIDE` and meaningful port sides per pin.** `_port_side` is heuristic; correct rotation/orientation hints would require per-symbol overrides we defer to v0.2.
- **Subprocess timeout 30s.** Should be plenty for our largest fixture (38 components); if a future fixture exceeds it, raise the limit or surface a meaningful error.

---

## Execution

Sequential: Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6. Per CLAUDE.md plan-review routing, this plan should be reviewed by `adversarial-reviewer` before implementation.
