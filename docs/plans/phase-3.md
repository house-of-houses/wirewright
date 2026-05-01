# Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HOLA the production placer with routing that doesn't pass wires through component bodies, and stand up the fixture-review machinery so the user's verdict-per-fixture log can drive Phase 4.

**Architecture reframe.** Phase 3's original DoD called for `routing/orthogonal.py` to wrap libavoid (Adaptagrams' object-avoiding orthogonal connector router). Recon at the start of this phase showed: no usable Python binding exists. `hola_graph` exposes only libavoid's geometry primitives (`Box`, `Polygon`), not the `Router`/`ConnRef` machinery. Writing a pybind11 wrapper around the C++ `Router` is its own multi-week project, disproportionate for v0.1. **Decision (recorded in this plan):** ship obstacle-aware L-shape routing in pure Python for v0.1. libavoid wrapper deferred until a real Python binding exists or until pure-Python routing's quality ceiling is hit.

Five tasks. (1) `docs/build-hola.md` documenting the wheel + source-build paths. (2) Obstacle-aware L-shape upgrade in `routing/orthogonal.py`: when a straight L between two pins would cross another component's bbox, choose the alternative L bend (vertical-first instead of horizontal-first, or vice versa) — picks whichever option avoids the most obstacles. Falls back to current behavior when both options collide. (3) Fixture scaffolding: a `description.md` template per tier + a `tools/add_fixture.py` helper. (4) Render-review tool: `wirewright review` produces a markdown table of all fixtures × placers with file size, component count, and a blank "verdict / failure category" column for the user. (5) Bump phase tracker; record Phase 3 status with the explicit libavoid deferral.

**Tech Stack:** Python 3.11, pytest, ruff, mypy, uv, `hola-graph >=0.1.5`. No new runtime deps.

**Out of scope (deferred):**
- libavoid integration (requires Python binding work).
- Hand-drawn `.asc` round-trip (gated on user authoring; not blocking Phase 3).
- HOLA pinned-hint support (Phase 4 deliverable).

---

## File Structure

| Path | Action | Responsibility |
|------|--------|----------------|
| `docs/build-hola.md` | Create | Wheel install path + source-build fallback for unsupported platforms. |
| `src/wirewright/routing/orthogonal.py` | Modify | Add `l_shape_avoiding(a, b, obstacles)` that picks the L-bend orientation that crosses the fewest obstacles. |
| `src/wirewright/placers/hola.py` | Modify | Use `l_shape_avoiding` for wire synthesis; pass component bboxes as obstacles. |
| `tests/unit/test_routing.py` | Modify | Tests for the obstacle-avoiding variant. |
| `tests/unit/test_hola.py` | Modify | Test that pin-routed wires don't cross other component bboxes (where avoidable). |
| `tools/add_fixture.py` | Create | CLI helper: `python tools/add_fixture.py <netlist.net> --tier easy --description "..."` copies the netlist into `tests/fixtures/<tier>/`, generates `description.md` from the template. |
| `tools/review.py` | Create | Renders every fixture × placer and emits a markdown verdict-table the user fills in. |
| `src/wirewright/cli.py` | Modify | Add `review` subcommand (or just point at the script). |
| `tests/fixtures/easy/_TEMPLATE.description.md` | Create | Template for per-fixture `description.md`. |
| `docs/PLAN.md` | Modify | Phase 3 status: complete in v0.1 (libavoid deferred per recon). |
| `CLAUDE.md` | Modify | Phase tracker: 3 complete; Phase 4 (patterns from failure log) starting. |

---

## Task 1: docs/build-hola.md

**Background.** Phase 3's original DoD listed `docs/build-hola.md` describing the pyhola build procedure. The `hola-graph` PyPI wheel covers macOS arm64 and Linux x86_64; for unsupported platforms (Linux arm64 wheels missing as of 0.1.5; Windows entirely; FreeBSD; etc.) source build is the path. Document it.

- [ ] **Step 1.1: Author the doc**

Create `docs/build-hola.md`:

```markdown
# Building hola-graph from source

For most users the [hola-graph PyPI wheel](https://pypi.org/project/hola-graph/) covers macOS arm64 and Linux x86_64 on Python 3.9–3.14. Just:

    uv add hola-graph                # or 'pip install hola-graph'

This installs `hola_graph`, which vendors the C++ adaptagrams stack (libcola, libavoid, libdialect, libvpsc) and exposes them via pybind11.

## When the wheel doesn't fit

Source build is required when:

- Your platform isn't covered by an upstream wheel (e.g. Linux arm64 as of 0.1.5, Windows, FreeBSD).
- You want to patch HOLA's C++ to fix one of the known abort cases (`tb303-vco-saw-cliptop`, `tb303-vco-integrated`).
- You want to build with debug symbols for HOLA development.

## Source-build steps

The upstream `shakfu/hola-graph` repository's `Makefile` does the right thing on macOS and Linux. Prerequisites: Python ≥3.9, a C++14 compiler, CMake ≥3.18.

```bash
git clone https://github.com/shakfu/hola-graph.git
cd hola-graph
make             # downloads adaptagrams, builds, installs to current Python
python -c "import hola_graph; print(hola_graph.__file__)"
```

The first build pulls and compiles `mjwybrow/adaptagrams` from source. Expect ~5 minutes on Apple Silicon, ~10 minutes on a slower x86_64.

## Pinning a known-good revision

In `pyproject.toml`'s `[project.optional-dependencies]` extra:

```toml
hola = ["hola-graph >=0.1.5"]
```

The `>=0.1.5` is the floor used in v0.1. Bumping to a later release should be safe but verify:

1. `tb303-voice-chain` still places successfully (was the bellwether for subprocess-isolation behavior).
2. The 3 known abort fixtures still abort *gracefully* (not silently — i.e. our `_run_hola_subprocess` still gets a non-zero exit code with a useful stderr).

## Reporting upstream issues

If a future fixture exposes a new C++ abort, file at https://github.com/shakfu/hola-graph/issues with:

- The fixture's parsed component+net list (use `wirewright render <fixture> --placer hola` and capture the subprocess stderr).
- A minimal `HolaGraph` Python script that reproduces the abort.

The upstream maintainer has historically been responsive (issues usually closed within weeks).
```

- [ ] **Step 1.2: Commit**

```bash
git add docs/build-hola.md
git commit -m "docs(build): document hola-graph wheel + source-build paths"
```

---

## Task 2: Obstacle-aware L-shape routing

**Background.** Current `l_shape(a, b)` in `routing/orthogonal.py` always picks horizontal-first. When the bend column happens to be inside another component's bbox, the wire crosses that component's body. With HOLA's compact layout this is the dominant readability problem.

**Algorithm.** For two endpoints `a` and `b`, two L-bend options exist: HV (horizontal-first, bend at `(b.x, a.y)`) and VH (vertical-first, bend at `(a.x, b.y)`). Pick the one whose two segments cross the fewest obstacle bboxes. Tie-break by HV (current behavior, deterministic).

A wire segment crosses a bbox iff the segment (a 1D extent on x or y) overlaps the bbox's projection on the wire's axis AND the wire's perpendicular coordinate falls inside the bbox.

**Files:**
- Modify: `src/wirewright/routing/orthogonal.py`
- Modify: `tests/unit/test_routing.py`
- Modify: `src/wirewright/placers/hola.py` (use the new function; build obstacle list from placed component bboxes)
- Modify: `tests/unit/test_hola.py`

- [ ] **Step 2.1: Tests for `l_shape_avoiding`**

Append to `tests/unit/test_routing.py`:

```python
def test_l_shape_avoiding_prefers_unobstructed_bend() -> None:
    from wirewright.routing.orthogonal import l_shape_avoiding

    # Endpoints (0, 0) and (96, 96). Two L options:
    #   HV: bend at (96, 0)  → segments (0,0)-(96,0) and (96,0)-(96,96)
    #   VH: bend at (0, 96)  → segments (0,0)-(0,96) and (0,96)-(96,96)
    # Obstacle covers the HV bend: bbox (32, -16, 80, 16).
    obstacles = [(32, -16, 80, 16)]
    wires = l_shape_avoiding((0, 0), (96, 96), obstacles)
    bend = (wires[0].x2, wires[0].y2)
    # Should have picked VH (bend at (0, 96)), avoiding the obstacle.
    assert bend == (0, 96)


def test_l_shape_avoiding_falls_back_to_hv_on_tie() -> None:
    from wirewright.routing.orthogonal import l_shape_avoiding

    # Both bends free. Default HV (horizontal first).
    wires = l_shape_avoiding((0, 0), (96, 96), [])
    assert (wires[0].x2, wires[0].y2) == (96, 0)


def test_l_shape_avoiding_colinear_returns_single_segment() -> None:
    from wirewright.routing.orthogonal import l_shape_avoiding

    wires = l_shape_avoiding((0, 64), (96, 64), [(32, 32, 80, 80)])
    assert len(wires) == 1
```

- [ ] **Step 2.2: Implementation**

In `src/wirewright/routing/orthogonal.py`, append:

```python
def _segments_crossings(
    seg: tuple[tuple[int, int], tuple[int, int]],
    obstacles: list[tuple[int, int, int, int]],
) -> int:
    """Count obstacles whose interior the segment crosses.

    Touching an obstacle edge does not count as crossing.
    """
    (x1, y1), (x2, y2) = seg
    crossings = 0
    for x_min, y_min, x_max, y_max in obstacles:
        if x1 == x2:
            # Vertical segment at x = x1.
            if x_min < x1 < x_max:
                lo, hi = min(y1, y2), max(y1, y2)
                if lo < y_max and hi > y_min:
                    crossings += 1
        else:
            # Horizontal segment at y = y1.
            if y_min < y1 < y_max:
                lo, hi = min(x1, x2), max(x1, x2)
                if lo < x_max and hi > x_min:
                    crossings += 1
    return crossings


def l_shape_avoiding(
    a: tuple[int, int],
    b: tuple[int, int],
    obstacles: list[tuple[int, int, int, int]],
) -> list[Wire]:
    """L-shape from ``a`` to ``b`` picking the bend that crosses fewest obstacles.

    Two options: HV (horizontal first, bend at ``(b.x, a.y)``) or VH
    (vertical first, bend at ``(a.x, b.y)``). Tie-break by HV (matches the
    legacy :func:`l_shape` behavior so existing tests stay deterministic).
    """
    ax, ay = snap_to_grid(a)
    bx, by = snap_to_grid(b)
    if ax == bx or ay == by:
        return [Wire(ax, ay, bx, by)]

    hv = [((ax, ay), (bx, ay)), ((bx, ay), (bx, by))]
    vh = [((ax, ay), (ax, by)), ((ax, by), (bx, by))]
    hv_cost = sum(_segments_crossings(s, obstacles) for s in hv)
    vh_cost = sum(_segments_crossings(s, obstacles) for s in vh)

    chosen = hv if hv_cost <= vh_cost else vh
    return [Wire(s[0][0], s[0][1], s[1][0], s[1][1]) for s in chosen]
```

- [ ] **Step 2.3: Wire HOLA to use it**

In `src/wirewright/placers/hola.py`, replace the `l_shape(...)` calls in the wire-synthesis loop with `l_shape_avoiding(..., obstacles)`. Build `obstacles` once after placement:

```python
from wirewright.routing.orthogonal import l_shape_avoiding, snap_to_grid

# After component placement, before wire synthesis:
obstacles: list[tuple[int, int, int, int]] = []
for c in out.components:
    geo = symbol_geometry(c.symbol)
    x_min, y_min, x_max, y_max = geo.bbox
    # Component-rotated bbox in canvas coords (R0 only in v0.1).
    obstacles.append((c.x + x_min, c.y + y_min, c.x + x_max, c.y + y_max))

# In the wire loop, replace l_shape(...) with l_shape_avoiding(..., obstacles).
```

Drop the now-unused `from wirewright.routing.orthogonal import l_shape` import.

- [ ] **Step 2.4: Test that HOLA wires don't cross component bbodies (where avoidable)**

Append to `tests/unit/test_hola.py`:

```python
def test_hola_wires_avoid_component_bodies_where_possible() -> None:
    """A 3-resistor chain has the canonical 'wire crosses middle component'
    failure mode in pairwise L-shape routing. Obstacle-aware routing should
    bend the connecting wire around R2's bbox.
    """
    s = Schematic(
        components=[
            Component(ref="R1", symbol="res", pins={"1": "vin", "2": "n1"}),
            Component(ref="R2", symbol="res", pins={"1": "n1", "2": "n2"}),
            Component(ref="R3", symbol="res", pins={"1": "n2", "2": "0"}),
        ],
        nets=[Net("vin"), Net("n1"), Net("n2"), Net("0", is_ground=True)],
    )
    placed = HolaPlacer().place(s)

    # Build placed-bbox set.
    from wirewright.symbols.builtin import symbol_geometry
    bboxes = {}
    for c in placed.components:
        geo = symbol_geometry(c.symbol)
        x_min, y_min, x_max, y_max = geo.bbox
        bboxes[c.ref] = (c.x + x_min, c.y + y_min, c.x + x_max, c.y + y_max)

    # No wire's interior should pass through R2's bbox unless R2 is the wire's
    # endpoint (a wire endpoint touching R2 = legitimate connection to its pin).
    r2_bbox = bboxes["R2"]
    r2_x_min, r2_y_min, r2_x_max, r2_y_max = r2_bbox
    for w in placed.wires:
        # Skip wires whose endpoints lie on R2's pin coordinates (those are
        # the legitimate connections to R2).
        endpoint_on_r2 = lambda x, y: r2_x_min <= x <= r2_x_max and r2_y_min <= y <= r2_y_max
        if endpoint_on_r2(w.x1, w.y1) or endpoint_on_r2(w.x2, w.y2):
            continue
        # Otherwise, this wire should not cross R2's interior.
        if w.x1 == w.x2:
            if r2_x_min < w.x1 < r2_x_max:
                lo, hi = min(w.y1, w.y2), max(w.y1, w.y2)
                assert not (lo < r2_y_max and hi > r2_y_min), (
                    f"wire {w} crosses R2 bbox {r2_bbox}"
                )
        else:
            if r2_y_min < w.y1 < r2_y_max:
                lo, hi = min(w.x1, w.x2), max(w.x1, w.x2)
                assert not (lo < r2_x_max and hi > r2_x_min), (
                    f"wire {w} crosses R2 bbox {r2_bbox}"
                )
```

- [ ] **Step 2.5: Run tests, commit**

```bash
uv run pytest tests/unit/test_routing.py tests/unit/test_hola.py -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add src/wirewright/routing/orthogonal.py src/wirewright/placers/hola.py tests/unit/test_routing.py tests/unit/test_hola.py
git commit -m "feat(routing): obstacle-aware L-shape; HOLA wires avoid component bodies"
```

---

## Task 3: Fixture scaffolding

**Background.** Phase 3 needs 8–12 expanded fixtures. The user authors netlists; the agent provides scaffolding (a per-fixture `description.md` and a CLI helper to drop new netlists into the right tier).

**Files:**
- Create: `tests/fixtures/_TEMPLATE.description.md`
- Create: `tools/add_fixture.py`

- [ ] **Step 3.1: Description template**

Create `tests/fixtures/_TEMPLATE.description.md`:

```markdown
# <fixture-name>

**Tier:** easy | medium | hard
**Components:** <count>
**Element types:** <e.g. R/C/V, R/C/D/B/E, R/C/D/Q/X/S, etc>

## What this circuit does

(2–3 sentences. Why this fixture is in the corpus and what placer behavior it
exercises.)

## Phase 3 verdict

(Filled in by the user after rendering and reviewing.)

- HOLA: ✓ acceptable | ⚠ needs-pattern | ⚠ needs-routing | ✗ HOLA-aborted
- Failure category (if not ✓): <one of: bypass-routing, no-symmetry, dense-feedback, dispersed-layout, other>
- Notes: ...

## Pattern hints (Phase 4)

(Filled in once Phase 3's verdict identifies needs-pattern entries. List the
analog idioms in the circuit that a pattern template should match.)

- e.g. NPN diff pair Q1/Q2
- e.g. PNP current mirror Q3/Q4 with diode-connected Q3
- e.g. RC low-pass on the VCF envelope
```

- [ ] **Step 3.2: Helper CLI**

Create `tools/add_fixture.py`:

```python
"""Drop a netlist into tests/fixtures/<tier>/ and scaffold its description.md.

Usage:
    python tools/add_fixture.py path/to/circuit.net --tier medium \\
        --description "Eurorack VCA core, 12 components"
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path, help="Path to source .net file")
    parser.add_argument(
        "--tier", choices=["easy", "medium", "hard"], required=True
    )
    parser.add_argument(
        "--description", default="", help="Short description for description.md"
    )
    args = parser.parse_args(argv)

    if not args.netlist.exists():
        print(f"netlist not found: {args.netlist}", file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parent.parent
    fixtures = repo_root / "tests/fixtures" / args.tier
    fixtures.mkdir(parents=True, exist_ok=True)

    dest_net = fixtures / args.netlist.name
    if dest_net.exists():
        print(f"already exists: {dest_net}", file=sys.stderr)
        return 1

    shutil.copy2(args.netlist, dest_net)

    template = (repo_root / "tests/fixtures/_TEMPLATE.description.md").read_text()
    description = template.replace(
        "# <fixture-name>", f"# {args.netlist.stem}"
    ).replace(
        "**Tier:** easy | medium | hard", f"**Tier:** {args.tier}"
    )
    if args.description:
        description = description.replace(
            "(2–3 sentences. Why this fixture is in the corpus and what placer behavior it\nexercises.)",
            args.description,
        )

    desc_path = fixtures / f"{args.netlist.stem}.description.md"
    desc_path.write_text(description)

    print(f"copied:  {dest_net}")
    print(f"created: {desc_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3.3: Commit**

```bash
git add tests/fixtures/_TEMPLATE.description.md tools/add_fixture.py
git commit -m "feat(fixtures): per-fixture description.md template + add_fixture helper"
```

---

## Task 4: Render-review tool

**Background.** Phase 3 needs the user's verdict-per-fixture log to drive Phase 4. Today the user runs `tools/render_compare.py` and inspects each `.asc` in LTspice. A markdown verdict-table makes the log structured.

**Files:**
- Create: `tools/review.py`

- [ ] **Step 4.1: Review tool**

Create `tools/review.py`:

```python
"""Render all fixtures via every placer and emit a markdown verdict table.

Usage:
    uv run python tools/review.py --out review.md
    uv run python tools/review.py --tier medium --out medium-review.md

The output table has rows = fixtures × placers, columns = fixture name,
placer, status (rendered / aborted / parse-error), file size, components
count, wire count, blank "verdict" and "category" columns for the user
to fill in after opening the .asc files in LTspice.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from wirewright.emit.asc import emit_asc
from wirewright.parse.spice import parse_spice_file
from wirewright.placers import get_placer, registry


def _render_one(fixture: Path, placer_name: str, out_dir: Path) -> dict[str, str]:
    """Render fixture+placer; return a row dict for the markdown table."""
    row = {
        "fixture": fixture.stem,
        "placer": placer_name,
        "status": "rendered",
        "size": "-",
        "components": "-",
        "wires": "-",
        "verdict": "",
        "category": "",
    }
    try:
        sch = parse_spice_file(fixture)
        placer = get_placer(placer_name)
        placed = placer.place(sch)
        asc_text = emit_asc(placed)
        out_path = out_dir / f"{fixture.stem}.{placer_name}.asc"
        out_path.write_text(asc_text)
        row.update(
            size=str(len(asc_text)),
            components=str(len(placed.components)),
            wires=str(len(placed.wires)),
        )
    except Exception as e:
        kind = type(e).__name__
        msg = str(e)[:80]
        row.update(status=f"FAILED ({kind}: {msg})")
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tier", choices=["easy", "medium", "hard", "all"], default="all"
    )
    parser.add_argument("--out", type=Path, default=Path("review.md"))
    parser.add_argument(
        "--asc-out", type=Path, default=Path("review_asc"),
        help="Where to write the rendered .asc files",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    fixtures_root = repo_root / "tests/fixtures"
    tiers = ["easy", "medium", "hard"] if args.tier == "all" else [args.tier]
    args.asc_out.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    for tier in tiers:
        for net in sorted((fixtures_root / tier).glob("*.net")):
            for placer_name in sorted(registry):
                rows.append(_render_one(net, placer_name, args.asc_out))

    # Emit the markdown table.
    md = ["# Render review", ""]
    md.append("Open each rendered `.asc` in LTspice. Fill in the **verdict**")
    md.append("(✓ acceptable / ⚠ needs-pattern / ⚠ needs-routing / ✗ aborted)")
    md.append("and **category** (bypass-routing / no-symmetry / dense-feedback /")
    md.append("dispersed-layout / other) per row. Phase 4 priorities draw from")
    md.append("the populated table.")
    md.append("")
    md.append("| fixture | placer | status | size | components | wires | verdict | category |")
    md.append("|---------|--------|--------|-----:|-----------:|------:|---------|----------|")
    for r in rows:
        md.append(
            f"| {r['fixture']} | {r['placer']} | {r['status']} | "
            f"{r['size']} | {r['components']} | {r['wires']} | "
            f"{r['verdict']} | {r['category']} |"
        )
    args.out.write_text("\n".join(md) + "\n")
    print(f"wrote {args.out} ({len(rows)} rows)")
    print(f"rendered .asc files in {args.asc_out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4.2: Smoke-test the review tool**

```bash
uv run python tools/review.py --tier easy --out /tmp/easy-review.md --asc-out /tmp/review_asc
head -30 /tmp/easy-review.md
```

Expected: a markdown table with rows for each (easy fixture, placer) combination, status filled, verdict/category blank.

- [ ] **Step 4.3: Commit**

```bash
git add tools/review.py
git commit -m "feat(tools): review.py renders all fixtures and emits markdown verdict table"
```

---

## Task 5: Mark Phase 3 done; bump tracker

**Files:**
- Modify: `docs/PLAN.md` Phase 3 status
- Modify: `CLAUDE.md` phase tracker

- [ ] **Step 5.1: PLAN.md status**

In `docs/PLAN.md` Phase 3 section, replace the existing **Status:** line with:

```markdown
**Status**: complete in v0.1. HOLA + subprocess isolation already shipped in
the spike (per ADR-0005). Routing improved with obstacle-aware L-shape
selection in `routing/orthogonal.py` (libavoid wrapper deferred — no
Python binding exists; pure-Python obstacle avoidance suffices for v0.1).
Fixture scaffolding: `tools/add_fixture.py` + per-fixture `description.md`
template. Review tool: `tools/review.py` produces a markdown verdict table.
The user-recorded failure log (filled in during fixture review) becomes
Phase 4's input.
```

- [ ] **Step 5.2: CLAUDE.md tracker**

```markdown
**Current phase**: 3 complete; Phase 4 (patterns from failure log) starting.
```

- [ ] **Step 5.3: Final smoke + commit**

```bash
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add docs/PLAN.md CLAUDE.md
git commit -m "docs: mark Phase 3 complete; libavoid deferred per recon"
```

---

## Self-Review

**Spec coverage:**
- HOLA placer working: already shipped in spike. ✓
- Routing improvement: Task 2 (obstacle-aware L-shape; libavoid deferred — explicit + documented). ✓
- `docs/build-hola.md`: Task 1. ✓
- Expanded fixtures with description.md per fixture: Task 3 (scaffolding; user authors). ✓ for scaffolding.
- Verdict + failure category recorded per fixture: Task 4 (tool produces the table; user fills in). ✓ for tooling.

**Placeholder scan:** none.

**Type consistency:** `obstacles: list[tuple[int, int, int, int]]` consistent across orthogonal.py and hola.py. `Wire` type unchanged.

**Risks:**
- `l_shape_avoiding` is a 2-option chooser, not a real router. It cannot route through narrow gaps or around multiple obstacles in one stroke. v0.2 may upgrade when libavoid bindings exist.
- Test `test_hola_wires_avoid_component_bodies_where_possible` may be flaky if HOLA's layout puts components such that BOTH L-bend options cross the obstacle. The test name says "where avoidable"; trust the chooser to do its best, but accept that some layouts are unavoidably-crossed.

---

## Execution

Sequential: Task 1 → Task 2 → Task 3 → Task 4 → Task 5. Per CLAUDE.md plan-review routing, run `adversarial-reviewer` before implementing.
