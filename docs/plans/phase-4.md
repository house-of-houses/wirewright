# Phase 4 Implementation Plan (rev 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the second real placer. `wirewright render <fixture> --placer hola` produces a valid `.asc` for the three canonical fixtures, with a side-by-side comparison tool that renders the same fixture under `naive`/`elk`/`hola` for visual inspection.

**Architecture:** Five tasks. (1) Add `hola-graph` to optional dependencies + import (recon already confirmed `pip install hola-graph`; ARM64 wheel ships from PyPI). (2) Implement `HolaPlacer`: build a `HolaGraph` with one node per Component (size from bbox), one edge per non-power/ground net pair, call `g.layout()`, read back node positions, snap to LTspice grid. **HOLA does not have port constraints** — it places nodes only. We synthesize wires post-layout by computing pin absolute positions and routing pairwise via `routing.orthogonal.l_shape` (same L-shape pattern naive uses). (3) Tests (unit + e2e). (4) Render canonical fixtures with the same Phase-3 verification bar (placement + .asc validity; full connectivity isomorphism on easy only). (5) Side-by-side comparison tool `tools/render_compare.py` and notes file `docs/notes/elk-vs-hola.md`.

**Tech Stack:** Python 3.11, pytest, ruff, mypy, uv, `hola-graph >=0.1.5`. The HOLA placer is enabled when the `hola` extra is installed (`uv add --extra hola`).

**Spec sources:**
- `docs/PLAN.md` Phase 4 (DoD: render all three fixtures via `--placer hola`, side-by-side tool works, opinion documented).
- `docs/specs/placer-interface.md` (stable in v0.1; HOLA section in "Hints recognized by specific back ends" needs filling in).
- `docs/adr/0004-elk-and-hola-as-baselines.md` (rationale).

**Out of scope (deferred):**
- Port-constrained layout in HOLA. HOLA's port-aware variant lives behind libdialect; v0.1 uses bare HOLA with post-layout routing.
- `pinned`, `aspect_ratio` hint passthrough. v0.3+.
- Detailed quality assessment vs ELK on every fixture. v0.1 ships honest opinion based on subjective comparison; quantitative metrics deferred.

---

## File Structure

| Path | Action | Responsibility |
|------|--------|----------------|
| `pyproject.toml` | Modify | `hola-graph >=0.1.5` to `[project.optional-dependencies] hola`. |
| `src/wirewright/placers/hola.py` | Rewrite | Implement `HolaPlacer.place()` using `hola_graph.HolaGraph`. |
| `tests/unit/test_hola.py` | Create | Unit tests for `HolaPlacer` (skipped when `hola_graph` not importable). |
| `tests/integration/test_hola_render.py` | Create | Integration: render canonical fixtures, validate placement + .asc validity. |
| `tools/render_compare.py` | Rewrite | Render the same fixture under naive/elk/hola; produce a side-by-side report (paths to .asc files + summary stats). |
| `docs/notes/elk-vs-hola.md` | Create | Honest opinion: which placer wins on which kinds of circuits. |
| `docs/PLAN.md` | Modify | Phase 4 status: complete. |
| `CLAUDE.md` | Modify | Phase tracker: 4 complete; Phase 5 starting. |

---

## Task 1: Add hola-graph dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1.1: Update optional-dependencies**

In `pyproject.toml`, replace the existing `hola` extra:

```toml
hola = ["hola-graph >=0.1.5"]
```

(Was `hola = ["pyhola"]` — that package was renamed to `hola-graph`.)

- [ ] **Step 1.2: Sync and verify**

```bash
uv add --optional hola "hola-graph>=0.1.5"  # equivalently: edit pyproject + uv lock
uv sync --extra hola --extra dev
uv run python3 -c "from hola_graph import HolaGraph; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 1.3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(hola): add hola-graph >=0.1.5 to optional-dependencies"
```

---

## Task 2: Implement HolaPlacer

**Background.** HOLA API:
- `g = HolaGraph()`
- `g.add_node(width: float, height: float, x: float | None, y: float | None, label: str | None) -> HolaNode`
- `g.connect(source: str | HolaNode, target: str | HolaNode)`
- `g.layout(opts: HolaOpts | None = None)` — modifies node positions in place
- Nodes expose `.x`, `.y`, `.width`, `.height`, `.label`

HOLA does NOT have ports. We give one node per Component (size = symbol bbox), one edge per non-power/ground net's pin pair, run layout, then synthesize wires by computing pin absolute positions and routing pairwise.

Component placement: HOLA returns node center coordinates; convert to IR component origin = `(node.x - bbox_width/2 + bbox_x_min, node.y - bbox_height/2 + bbox_y_min)`. Verify the convention (HOLA may return top-left or center — check via smoke). Snap to grid.

**Files:**
- Modify: `src/wirewright/placers/hola.py`
- Create: `tests/unit/test_hola.py`

- [ ] **Step 2.1: Smoke-test HolaGraph node-position convention**

Run a one-off check to confirm whether `node.x`/`node.y` is top-left or center after layout:

```python
from hola_graph import HolaGraph
g = HolaGraph()
n = g.add_node(40, 60, x=100, y=200, label="probe")
print(n.x, n.y, "bounds=", n.bounds, "position=", n.position)
g.layout()
print("after:", n.x, n.y, n.bounds)
```

Document the convention here in the plan based on the result. From the API help (`add_node(... x: 'Optional x position.', y: 'Optional y position.')`) it appears `x`/`y` is the position the user provides directly without specifying convention. Empirical check needed.

- [ ] **Step 2.2: Write failing unit tests**

Create `tests/unit/test_hola.py`:

```python
"""Tests for the HOLA placer."""

from __future__ import annotations

import pytest

pytest.importorskip("hola_graph")  # skip whole module when extra not installed

from wirewright.ir.model import Component, Net, Schematic
from wirewright.placers.hola import HolaPlacer


def _two_resistor() -> Schematic:
    return Schematic(
        components=[
            Component(ref="R1", symbol="res", value="10k", pins={"1": "vin", "2": "n1"}),
            Component(ref="R2", symbol="res", value="10k", pins={"1": "n1", "2": "0"}),
        ],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
    )


def test_hola_places_every_component() -> None:
    placed = HolaPlacer().place(_two_resistor())
    assert placed.is_placed


def test_hola_grid_aligned() -> None:
    placed = HolaPlacer().place(_two_resistor())
    for c in placed.components:
        assert c.x is not None and c.x % 16 == 0
        assert c.y is not None and c.y % 16 == 0


def test_hola_does_not_mutate_input() -> None:
    s = _two_resistor()
    original_refs = {c.ref for c in s.components}
    HolaPlacer().place(s)
    # Input still has all components unplaced.
    assert {c.ref for c in s.components} == original_refs
    for c in s.components:
        assert c.x is None and c.y is None


def test_hola_emits_ground_flags() -> None:
    placed = HolaPlacer().place(_two_resistor())
    # R2.pin2 maps to ground "0" → at least one FLAG with net "0".
    assert any(f.net == "0" for f in placed.flags)


def test_hola_unknown_symbol_raises_placer_error() -> None:
    from wirewright.placers.base import PlacerError

    s = Schematic(
        components=[Component(ref="X1", symbol="not_real", pins={"a": "n1"})],
        nets=[Net("n1")],
    )
    with pytest.raises(PlacerError, match="unknown symbol"):
        HolaPlacer().place(s)
```

Run: `uv run pytest tests/unit/test_hola.py -v` — expected: all fail (HolaPlacer is still stubbed).

- [ ] **Step 2.3: Implementation**

Replace `src/wirewright/placers/hola.py` with:

```python
"""HOLA (Human-like Orthogonal Layout) placer adapter.

Uses the ``hola_graph`` Python package (https://github.com/shakfu/hola-graph,
the renamed ``pyhola``). HOLA does not have port constraints; we build one
node per Component, one edge per non-power/ground net pair, run layout,
then synthesize wires by routing pairwise between pin absolute positions.

Power and ground nets are emitted as global rails (FLAGs at every
connecting pin), not HOLA edges.
"""

from __future__ import annotations

import copy
from typing import Any

from wirewright.ir.model import Flag, Schematic, Wire
from wirewright.ir.validate import LTSPICE_GRID, validate, validate_placed
from wirewright.placers.base import Placer, PlacerEngineError, PlacerError
from wirewright.routing.orthogonal import l_shape, snap_to_grid
from wirewright.symbols.builtin import absolute_pin_position, symbol_geometry


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

        # Build the HOLA graph: one node per component (size from symbol bbox).
        g = HolaGraph()
        for c in out.components:
            try:
                geo = symbol_geometry(c.symbol)
            except KeyError as e:
                raise PlacerError(
                    f"Component {c.ref!r}: unknown symbol {c.symbol!r}"
                ) from e
            x_min, y_min, x_max, y_max = geo.bbox
            width = max(x_max - x_min, LTSPICE_GRID)
            height = max(y_max - y_min, LTSPICE_GRID)
            g.add_node(width=float(width), height=float(height), label=c.ref)

        # Edges: one per non-power/ground net's pin pair (pairwise; HOLA does
        # not aggregate hyper-edges).
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

        g.layout()

        # Read positions back and assign component origins. HOLA's node.x /
        # node.y is the geometric CENTER of the node's bbox; node.bounds is
        # (left, top, right, bottom) in canvas coords. Component origin (LTspice
        # SYMBOL position) = bbox-canvas-top-left - bbox-symbol-top-left.
        for c in out.components:
            node = g.node(c.ref)
            geo = symbol_geometry(c.symbol)
            left, top, _right, _bottom = node.bounds
            sx, sy = snap_to_grid(
                (int(round(left)) - geo.bbox[0], int(round(top)) - geo.bbox[1])
            )
            c.x, c.y = sx, sy
            c.orientation = "R0"

        # Synthesize wires by routing pairwise between pin absolute positions.
        # Skip self-loops (multiple pins of same net on same component — rare but
        # legal); the wire would route through the component body.
        out.wires = []
        for net_name in net_to_refs:
            pin_positions: list[tuple[int, int]] = []
            for c in out.components:
                for pin_name, pn in c.pins.items():
                    if pn == net_name:
                        assert c.x is not None and c.y is not None
                        pin_positions.append(
                            absolute_pin_position(
                                (c.x, c.y), c.symbol, pin_name, c.orientation
                            )
                        )
            distinct_positions = {p for p in pin_positions}
            if len(distinct_positions) < 2:
                continue
            anchor = pin_positions[0]
            for target in pin_positions[1:]:
                if target == anchor:
                    continue
                out.wires.extend(l_shape(anchor, target))

        # Power/ground rails as flags + stub wires.
        out.flags = []
        nets_by_name = {n.name: n for n in out.nets}
        for c in out.components:
            assert c.x is not None and c.y is not None, f"{c.ref!r} unplaced"
            for pin_name, net_name in c.pins.items():
                net = nets_by_name.get(net_name)
                if net is None:
                    continue
                pos = absolute_pin_position(
                    (c.x, c.y), c.symbol, pin_name, c.orientation
                )
                if net.is_ground or net.name == "0":
                    stub_y = pos[1] + LTSPICE_GRID * 2
                    out.wires.append(Wire(pos[0], pos[1], pos[0], stub_y))
                    out.flags.append(Flag(pos[0], stub_y, "0"))
                elif net.is_power:
                    out.flags.append(Flag(pos[0], pos[1], net.name))

        # Drop zero-length wires (snap collapses) before validating.
        out.wires = [w for w in out.wires if (w.x1, w.y1) != (w.x2, w.y2)]

        validate_placed(out)
        return out
```

- [ ] **Step 2.4: Run unit tests, commit**

```bash
uv run pytest tests/unit/test_hola.py -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add src/wirewright/placers/hola.py tests/unit/test_hola.py
git commit -m "feat(hola): implement HolaPlacer via hola-graph"
```

---

## Task 3: Integration tests on canonical fixtures

**Files:**
- Create: `tests/integration/test_hola_render.py`

- [ ] **Step 3.1: Create integration test**

Create `tests/integration/test_hola_render.py` (parallel to `test_elk_render.py`):

```python
"""Render canonical fixtures via HOLA and verify placement + .asc validity."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

pytest.importorskip("hola_graph")

from wirewright.emit.asc import emit_asc
from wirewright.ir.model import Schematic
from wirewright.parse.ltspice_asc import parse_asc_text
from wirewright.parse.spice import parse_spice_file
from wirewright.placers.hola import HolaPlacer


def _connectivity_signature(s: Schematic) -> dict[str, frozenset[tuple[str, str]]]:
    sig: dict[str, set[tuple[str, str]]] = {}
    for c in s.components:
        for pin_name, net_name in c.pins.items():
            sig.setdefault(net_name, set()).add((c.ref, pin_name))
    return {k: frozenset(v) for k, v in sig.items()}


@pytest.mark.parametrize(
    "fixture_relpath",
    [
        "easy/divider.net",
        "medium/tb303-envelope.net",
        "hard/tb303-vco-integrated.net",
    ],
)
def test_hola_renders_canonical_fixture(fixture_relpath: str) -> None:
    fixture = Path(__file__).resolve().parents[2] / "tests/fixtures" / fixture_relpath
    if not fixture.exists():
        pytest.skip(f"fixture not present: {fixture_relpath}")

    parsed_input = parse_spice_file(cast(Path, fixture))
    placed = HolaPlacer().place(parsed_input)
    assert placed.is_placed
    assert {c.ref for c in placed.components} == {c.ref for c in parsed_input.components}

    asc_text = emit_asc(placed)
    reparsed = parse_asc_text(asc_text)
    assert {c.ref for c in reparsed.components} == {c.ref for c in placed.components}

    if fixture_relpath.startswith("easy/"):
        sig_in = _connectivity_signature(placed)
        sig_out = _connectivity_signature(reparsed)
        multiset_in = sorted(tuple(sorted(s)) for s in sig_in.values())
        multiset_out = sorted(tuple(sorted(s)) for s in sig_out.values())
        assert multiset_in == multiset_out, (
            f"connectivity changed across round-trip for {fixture_relpath}"
        )
```

- [ ] **Step 3.2: Run, commit**

```bash
uv run pytest tests/integration/test_hola_render.py -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add tests/integration/test_hola_render.py
git commit -m "test(hola): canonical fixture integration tests"
```

---

## Task 4: Side-by-side comparison tool

**Background.** `tools/render_compare.py` already exists as a stub. Replace with a tool that runs all three placers on a given fixture (or all canonical fixtures) and produces an output directory with the `.asc` files plus a summary.

**Files:**
- Modify: `tools/render_compare.py`

- [ ] **Step 4.1: Implement render_compare**

Replace `tools/render_compare.py` with:

```python
"""Side-by-side placer comparison.

Renders the given fixture (or every fixture in a directory) under each
available placer and writes results to an output directory. Each placer's
output goes to ``<out>/<fixture-stem>.<placer>.asc``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wirewright.emit.asc import write_asc
from wirewright.parse.spice import parse_spice_file
from wirewright.placers import get_placer, registry


def _render_one(fixture: Path, placer_name: str, out_dir: Path) -> Path | None:
    """Render fixture under the named placer; return path or None on failure."""
    try:
        sch = parse_spice_file(fixture)
        placer = get_placer(placer_name)
        placed = placer.place(sch)
    except Exception as e:
        print(f"  {placer_name}: FAILED ({type(e).__name__}: {e})", file=sys.stderr)
        return None
    out_path = out_dir / f"{fixture.stem}.{placer_name}.asc"
    write_asc(placed, out_path)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        help="Fixture file or directory of fixtures",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("compare_out"),
        help="Output directory (default: ./compare_out)",
    )
    parser.add_argument(
        "--placers",
        nargs="+",
        default=sorted(registry),
        help="Placers to compare (default: all registered)",
    )
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    fixtures: list[Path] = (
        sorted(args.input.glob("*.net")) if args.input.is_dir() else [args.input]
    )

    for fixture in fixtures:
        print(f"=== {fixture.name}")
        for placer_name in args.placers:
            out_path = _render_one(fixture, placer_name, args.out)
            if out_path is not None:
                print(f"  {placer_name}: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4.2: Smoke-test the comparison tool**

```bash
uv run python tools/render_compare.py tests/fixtures/easy/divider.net --out /tmp/cmp
ls /tmp/cmp
```

Expected: three files `divider.naive.asc`, `divider.elk.asc`, `divider.hola.asc`.

- [ ] **Step 4.3: Commit**

```bash
git add tools/render_compare.py
git commit -m "feat(tools): render_compare runs all placers on the same fixture"
```

---

## Task 5: Honest opinion + spec finalize + tracker bump

**Files:**
- Create: `docs/notes/elk-vs-hola.md`
- Modify: `docs/specs/placer-interface.md`
- Modify: `docs/PLAN.md`
- Modify: `CLAUDE.md`

- [ ] **Step 5.1: Author the comparison note**

Render every canonical fixture with `render_compare.py` first, open the resulting `.asc` files in LTspice, then write `docs/notes/elk-vs-hola.md` based on what you actually see. Suggested template:

```markdown
# ELK vs HOLA: when to pick which

Ran `uv run python tools/render_compare.py tests/fixtures/{easy,medium,hard}` and opened the resulting `.asc` files in LTspice.

## Easy fixture (`divider.net`, 3 components)

[Observation about ELK]
[Observation about HOLA]
[Verdict for this complexity tier]

## Medium fixture (`tb303-envelope.net`, 20 components, R/C/D/B/E)

...

## Hard fixture (`tb303-vco-integrated.net`, 38 components, with subckts and BJTs)

...

## Recommendation by circuit kind

- **Strongly directional (signal chain, CV processor)**: ELK (Sugiyama produces clean layered output).
- **Symmetric analog (diff pair, current mirror, ladder)**: HOLA (stress-majorization preserves symmetry).
- **Mostly two-terminal RC blocks (envelope generator, VCF ladder)**: ...
- **Heavy transistor blocks (expo converter, voice chain)**: ...

## Caveats

- Both placers ship without port-constrained routing in v0.1; expect wire spaghetti on dense circuits. v0.3+ may add libavoid for orthogonal routing.
- HOLA's bare output is tested; v0.2 may explore libdialect's port-aware variant for closer-to-human results.
```

- [ ] **Step 5.2: Update placer-interface.md HOLA section**

In `docs/specs/placer-interface.md`'s "Hints recognized by specific back ends > hola" section, replace "Phase 4 deliverable; currently raises `NotImplementedError`" with the v0.1 contract:

```markdown
### hola
- Does not recognize `direction`, `aspect_ratio`, or `pinned` in v0.1 (HOLA is unconstrained stress-majorization). Hints are silently ignored.
- Requires the optional `hola` extra: `uv sync --extra hola`.
- Failure modes: `hola_graph` not importable → `PlacerEngineError` with install instructions.
```

- [ ] **Step 5.3: Mark Phase 4 done in PLAN.md**

Add `**Status**: complete in v0.1.` after Phase 4's "Depends on: Phase 3." line. Note any v0.1 caveats (HOLA's bare output is what ships; libdialect port-aware variant is v0.2+).

- [ ] **Step 5.4: Bump phase tracker**

```markdown
**Current phase**: 4 complete; Phase 5 (pattern recognition) starting.
```

- [ ] **Step 5.5: Final smoke + commit**

```bash
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add docs/notes/elk-vs-hola.md docs/specs/placer-interface.md docs/PLAN.md CLAUDE.md
git commit -m "feat(hola): Phase 4 complete — HOLA placer ships; comparison tool + opinion"
```

---

## Self-Review

**Spec coverage:**
- HOLA placer implementing `Placer` contract: Task 2. ✓
- Render canonical fixtures via `--placer hola`: Task 3. ✓
- Side-by-side comparison tool: Task 4. ✓
- Documented opinion: Task 5.1. ✓
- Phase 4 may slip per ADR-0004: not slipping; hola-graph PyPI wheel available. ✓

**Placeholder scan:** Step 5.1 has a "fill in based on what you see" template — that's expected since the opinion is empirical. Concrete enough for the writer.

**Type consistency:** `HolaGraph`, `HolaNode` from `hola_graph` package; `Component`, `Net`, `Schematic`, `Wire`, `Flag` from IR; `l_shape`, `snap_to_grid` from `routing.orthogonal`. All consistent across tasks.

**Risk:** HOLA's `node.x/y` convention (top-left vs center) is verified empirically in Step 2.1 before the implementation in 2.3 commits to it. If the convention turns out to be center, the formula `node.x - bbox[0]` becomes `node.x - width/2 + bbox[0]` (or similar). Step 2.1 surfaces this before code lands.

---

## Execution

Sequential: Task 1 → Task 2 → Task 3 → Task 4 → Task 5. Per CLAUDE.md plan-review routing, this plan is reviewed by `adversarial-reviewer` before implementation.
