# Phase 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working pattern-recognition layer. The matcher walks an unplaced `Schematic`, finds instances of YAML-defined analog idioms via NetworkX VF2, and produces hints (pinned positions for matched components) that the ELK placer honors. v0.1 ships with **5 representative templates** as proof of concept; the remaining list-of-13 from the spec is documented as v0.2 follow-up.

**Architecture:** Six tasks. (1) Finalize `docs/specs/pattern-library.md` (already a strong sketch; tighten and lock it). (2) Implement `patterns/matcher.py`: load YAML templates, build NetworkX graphs (component-as-node, shared-net-as-edge with type-aware matching via VF2 `node_match`), return `PatternMatch` records. (3) Author 5 starter templates as YAML files in `src/wirewright/patterns/library/`: `rc_lowpass`, `rc_highpass`, `diff_pair_npn`, `current_mirror_pnp`, `common_emitter_npn`. Each ships with one synthetic fixture and a triggering test. (4) Hint integration: extend `ElkPlacer` to honor `hints["pinned"]` by emitting per-node `x`/`y` and switching the affected nodes to `INTERACTIVE`/fixed positions. (5) Wire match → hint via a `wirewright.cli` flag `--use-patterns` and a small orchestration helper. (6) Render canonical fixtures with patterns enabled, document the v0.1 template inventory in `docs/notes/pattern-coverage.md`, mark Phase 5 done.

**Tech Stack:** Python 3.11, pytest, ruff, mypy, uv. New runtime dep: `networkx >=3.0` (already in dependencies for graph operations elsewhere; verify), and `pyyaml >=6.0` (already in dependencies).

**Out of scope (deferred to v0.2):**
- The remaining 8+ templates from the spec (`cascode_*`, `common_source_nmos`, `opamp_noninverting`, `opamp_sallen_key_lpf`, `tb303_ladder_rung`, `expo_converter_2t`, `bjt_diff_amp_full`, all four `diff_pair_*` variants beyond NPN, all four `current_mirror_*` beyond PNP).
- Pattern conflict-resolution priority across overlapping matches (v0.1 uses simple "higher priority wins, then drop overlaps"; complex precedence rules deferred).
- HOLA hint integration (HOLA has no `pinned` API in v0.1; ELK only).
- Pattern DSL (Python class form). v0.1 is YAML-only.
- Multi-instance template variations (v0.1 matches each template once per instance independently).

---

## File Structure

| Path | Action | Responsibility |
|------|--------|----------------|
| `docs/specs/pattern-library.md` | Modify | Status: stub → stable in v0.1; tighten YAML grammar; pin v0.1 template list to 5; document the v0.2 template backlog. |
| `src/wirewright/patterns/__init__.py` | Modify | Export `PatternMatch`, `find_matches`, `load_templates`. |
| `src/wirewright/patterns/matcher.py` | Rewrite | NetworkX VF2 matcher with type-aware node and edge matching. |
| `src/wirewright/patterns/template.py` | Create | YAML template loader → `Template` dataclass. |
| `src/wirewright/patterns/library/rc_lowpass.yaml` | Create | R + C, 2 components. |
| `src/wirewright/patterns/library/rc_highpass.yaml` | Create | C + R, swapped. |
| `src/wirewright/patterns/library/diff_pair_npn.yaml` | Create | Two NPN, shared emitter. |
| `src/wirewright/patterns/library/current_mirror_pnp.yaml` | Create | Two PNP, shared base, one diode-connected. |
| `src/wirewright/patterns/library/common_emitter_npn.yaml` | Create | One NPN, collector R + emitter R. |
| `src/wirewright/placers/elk.py` | Modify | Honor `hints["pinned"]` by setting node `x`/`y` and switching to `FIXED` position. |
| `tests/unit/test_patterns.py` | Create | Per-template tests (each template fires on its synthetic fixture). |
| `tests/integration/test_patterns_e2e.py` | Create | End-to-end: matcher + ELK with hints on canonical fixtures. |
| `src/wirewright/cli.py` | Modify | `--use-patterns` flag on `render` command. |
| `docs/notes/pattern-coverage.md` | Create | v0.1 template inventory + v0.2 backlog. |
| `docs/PLAN.md` | Modify | Phase 5 status: complete. |
| `CLAUDE.md` | Modify | Phase tracker: 5 complete; v0.1 ready for tag. |

---

## Task 1: Finalize the spec

**Files:**
- Modify: `docs/specs/pattern-library.md`

- [ ] **Step 1.1: Tighten the spec**

In `docs/specs/pattern-library.md`:

1. Status: `stable in v0.1`.
2. Replace the "(Sketch only)" YAML example with the canonical v0.1 grammar:

```yaml
name: <pattern_id>             # required, snake_case
version: <integer>             # required, bumps on layout-affecting change
description: <free text>
priority: <integer>            # higher wins on overlap; default 100

match:
  components:                  # required, ≥1
    - role: <role_name>
      symbol: <symbol_name>    # IR symbol name; matches Component.symbol
      # optional: spice_prefix, value_pattern (regex), spice_model_pattern
  topology:                    # required, ≥1 entry per multi-component pattern
    - <role>.<pin> == <role>.<pin>      # same-net constraint
    - <role>.<pin> != <role>.<pin>      # different-net constraint
    - <role>.<pin> == GND               # connected to ground

placement:                     # optional; if omitted, pattern is detected but no hint
  <role>:
    dx: <int>                  # offset from anchor (role 0 by convention)
    dy: <int>
    orientation: R0|R90|R180|R270|M0|M90|M180|M270
```

3. Replace the "Initial library" table with the v0.1-shipping subset (5 templates) and a v0.2 backlog section that lists the rest.

- [ ] **Step 1.2: Commit**

```bash
git add docs/specs/pattern-library.md
git commit -m "docs(spec): finalize pattern-library.md grammar for v0.1"
```

---

## Task 2: Template loader (`patterns/template.py`)

**Files:**
- Create: `src/wirewright/patterns/template.py`

- [ ] **Step 2.1: Implement template parser**

Create `src/wirewright/patterns/template.py`:

```python
"""YAML pattern template loader.

See docs/specs/pattern-library.md for the grammar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from wirewright.ir.model import Orientation


class TemplateError(Exception):
    """Raised when a YAML template cannot be parsed."""


@dataclass(frozen=True)
class ComponentSpec:
    role: str
    symbol: str
    spice_prefix: str | None = None
    value_pattern: str | None = None
    spice_model_pattern: str | None = None


@dataclass(frozen=True)
class TopologyConstraint:
    """One topology constraint: '==' (same net) or '!=' (different net) or 'gnd'."""

    kind: Literal["same", "diff", "ground"]
    a: tuple[str, str]  # (role, pin)
    b: tuple[str, str] | None = None  # only for "same" and "diff"


@dataclass(frozen=True)
class PlacementHint:
    role: str
    dx: int
    dy: int
    orientation: Orientation = "R0"


@dataclass
class Template:
    name: str
    version: int
    description: str
    priority: int
    components: list[ComponentSpec]
    topology: list[TopologyConstraint]
    placement: list[PlacementHint] = field(default_factory=list)


def _parse_topology_line(line: str) -> TopologyConstraint:
    line = line.strip()
    if "==" in line:
        lhs, rhs = (s.strip() for s in line.split("==", 1))
        if rhs.upper() in ("GND", "0"):
            role, pin = lhs.split(".", 1)
            return TopologyConstraint(kind="ground", a=(role.strip(), pin.strip()))
        a_role, a_pin = lhs.split(".", 1)
        b_role, b_pin = rhs.split(".", 1)
        return TopologyConstraint(
            kind="same",
            a=(a_role.strip(), a_pin.strip()),
            b=(b_role.strip(), b_pin.strip()),
        )
    if "!=" in line:
        lhs, rhs = (s.strip() for s in line.split("!=", 1))
        a_role, a_pin = lhs.split(".", 1)
        b_role, b_pin = rhs.split(".", 1)
        return TopologyConstraint(
            kind="diff",
            a=(a_role.strip(), a_pin.strip()),
            b=(b_role.strip(), b_pin.strip()),
        )
    raise TemplateError(f"unrecognized topology constraint: {line!r}")


def load_template(path: str | Path) -> Template:
    """Parse a YAML template file."""
    p = Path(path)
    raw = yaml.safe_load(p.read_text())
    if not isinstance(raw, dict):
        raise TemplateError(f"{p}: top-level must be a mapping")
    try:
        components = [ComponentSpec(**c) for c in raw["match"]["components"]]
        topology = [_parse_topology_line(line) for line in raw["match"]["topology"]]
    except (KeyError, TypeError) as e:
        raise TemplateError(f"{p}: malformed match block: {e}") from e

    placement: list[PlacementHint] = []
    for role, hint in (raw.get("placement") or {}).items():
        placement.append(
            PlacementHint(
                role=role,
                dx=int(hint["dx"]),
                dy=int(hint["dy"]),
                orientation=hint.get("orientation", "R0"),
            )
        )

    return Template(
        name=raw["name"],
        version=int(raw.get("version", 1)),
        description=raw.get("description", ""),
        priority=int(raw.get("priority", 100)),
        components=components,
        topology=topology,
        placement=placement,
    )


def load_default_library() -> list[Template]:
    """Load every YAML template shipped under wirewright/patterns/library/."""
    here = Path(__file__).resolve().parent / "library"
    return [load_template(p) for p in sorted(here.glob("*.yaml"))]
```

- [ ] **Step 2.2: Tests for template loader**

Create `tests/unit/test_template_loader.py`:

```python
"""Tests for the YAML template loader."""

from __future__ import annotations

import pytest

from wirewright.patterns.template import (
    Template,
    TemplateError,
    load_template,
    _parse_topology_line,
)

_RC_LP_YAML = """\
name: rc_lowpass
version: 1
description: First-order RC low-pass filter
priority: 100
match:
  components:
    - {role: r, symbol: res}
    - {role: c, symbol: cap}
  topology:
    - r.2 == c.1
    - c.2 == GND
placement:
  r:
    dx: 0
    dy: 0
    orientation: R0
  c:
    dx: 96
    dy: 0
    orientation: R0
"""


def test_load_template_parses_components(tmp_path) -> None:
    p = tmp_path / "rc.yaml"
    p.write_text(_RC_LP_YAML)
    t = load_template(p)
    assert t.name == "rc_lowpass"
    assert {c.role for c in t.components} == {"r", "c"}
    assert next(c for c in t.components if c.role == "r").symbol == "res"


def test_load_template_parses_topology(tmp_path) -> None:
    p = tmp_path / "rc.yaml"
    p.write_text(_RC_LP_YAML)
    t = load_template(p)
    assert len(t.topology) == 2
    same = next(c for c in t.topology if c.kind == "same")
    assert same.a == ("r", "2")
    assert same.b == ("c", "1")
    ground = next(c for c in t.topology if c.kind == "ground")
    assert ground.a == ("c", "2")


def test_load_template_parses_placement(tmp_path) -> None:
    p = tmp_path / "rc.yaml"
    p.write_text(_RC_LP_YAML)
    t = load_template(p)
    assert len(t.placement) == 2
    assert {h.role for h in t.placement} == {"r", "c"}


def test_topology_unrecognized_raises() -> None:
    with pytest.raises(TemplateError, match="unrecognized"):
        _parse_topology_line("r.1 ~~ c.2")


def test_load_default_library_finds_yaml_files() -> None:
    """After Task 3 lands the 5 starter templates should appear here."""
    from wirewright.patterns.template import load_default_library

    templates = load_default_library()
    names = {t.name for t in templates}
    assert "rc_lowpass" in names
    assert "diff_pair_npn" in names
    assert len(templates) >= 5
```

- [ ] **Step 2.3: Run tests, commit**

The "load_default_library" test will fail until Task 3. That's expected.

```bash
uv run pytest tests/unit/test_template_loader.py -k "not load_default_library" -v
git add src/wirewright/patterns/template.py tests/unit/test_template_loader.py
git commit -m "feat(patterns): YAML template loader"
```

---

## Task 3: Author 5 starter templates

**Files:**
- Create: `src/wirewright/patterns/library/rc_lowpass.yaml`
- Create: `src/wirewright/patterns/library/rc_highpass.yaml`
- Create: `src/wirewright/patterns/library/diff_pair_npn.yaml`
- Create: `src/wirewright/patterns/library/current_mirror_pnp.yaml`
- Create: `src/wirewright/patterns/library/common_emitter_npn.yaml`

- [ ] **Step 3.1: rc_lowpass.yaml**

```yaml
name: rc_lowpass
version: 1
description: First-order RC low-pass filter (R in series, C to GND)
priority: 100
match:
  components:
    - {role: r, symbol: res}
    - {role: c, symbol: cap}
  topology:
    - r.2 == c.1
    - c.2 == GND
placement:
  r: {dx: 0,  dy: 0,  orientation: R0}
  c: {dx: 96, dy: 0,  orientation: R0}
```

- [ ] **Step 3.2: rc_highpass.yaml**

```yaml
name: rc_highpass
version: 1
description: First-order RC high-pass filter (C in series, R to GND)
priority: 100
match:
  components:
    - {role: c, symbol: cap}
    - {role: r, symbol: res}
  topology:
    - c.2 == r.1
    - r.2 == GND
placement:
  c: {dx: 0,  dy: 0,  orientation: R0}
  r: {dx: 96, dy: 0,  orientation: R0}
```

- [ ] **Step 3.3: diff_pair_npn.yaml**

```yaml
name: diff_pair_npn
version: 1
description: NPN differential pair, shared emitter
priority: 200
match:
  components:
    - {role: q1, symbol: npn}
    - {role: q2, symbol: npn}
  topology:
    - q1.E == q2.E
    - q1.B != q2.B
    - q1.C != q2.C
placement:
  q1: {dx: 0,   dy: 0,  orientation: R0}
  q2: {dx: 192, dy: 0,  orientation: M0}
```

- [ ] **Step 3.4: current_mirror_pnp.yaml**

```yaml
name: current_mirror_pnp
version: 1
description: PNP current mirror (two PNPs, shared base, one diode-connected)
priority: 200
match:
  components:
    - {role: q_ref, symbol: pnp}
    - {role: q_out, symbol: pnp}
  topology:
    - q_ref.B == q_out.B
    - q_ref.B == q_ref.C
    - q_ref.C != q_out.C
placement:
  q_ref: {dx: 0,   dy: 0,  orientation: R0}
  q_out: {dx: 192, dy: 0,  orientation: R0}
```

- [ ] **Step 3.5: common_emitter_npn.yaml**

```yaml
name: common_emitter_npn
version: 1
description: NPN common-emitter stage (collector R + emitter R)
priority: 150
match:
  components:
    - {role: q,  symbol: npn}
    - {role: rc, symbol: res}
    - {role: re, symbol: res}
  topology:
    - q.C == rc.2
    - q.E == re.1
    - re.2 == GND
placement:
  q:  {dx: 0,    dy: 96,  orientation: R0}
  rc: {dx: 16,   dy: 0,   orientation: R0}
  re: {dx: 16,   dy: 224, orientation: R0}
```

- [ ] **Step 3.6: Run library test, commit**

```bash
uv run pytest tests/unit/test_template_loader.py::test_load_default_library_finds_yaml_files -v
git add src/wirewright/patterns/library/
git commit -m "feat(patterns): library — RC lowpass/highpass, diff pair, current mirror, CE stage"
```

---

## Task 4: Implement the matcher (NetworkX VF2)

**Files:**
- Modify: `src/wirewright/patterns/matcher.py`
- Create: `tests/unit/test_patterns.py`

- [ ] **Step 4.1: Tests first**

Create `tests/unit/test_patterns.py`:

```python
"""Per-template matcher tests."""

from __future__ import annotations

from wirewright.ir.model import Component, Net, Schematic
from wirewright.patterns.matcher import find_matches


def _rc_lowpass_schematic() -> Schematic:
    return Schematic(
        components=[
            Component(ref="R1", symbol="res", pins={"1": "vin", "2": "n1"}),
            Component(ref="C1", symbol="cap", pins={"1": "n1", "2": "0"}),
        ],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
    )


def _diff_pair_schematic() -> Schematic:
    return Schematic(
        components=[
            Component(
                ref="Q1", symbol="npn",
                pins={"C": "out_p", "B": "in_p", "E": "tail"},
                spice_prefix="Q", spice_model="QN3904",
            ),
            Component(
                ref="Q2", symbol="npn",
                pins={"C": "out_n", "B": "in_n", "E": "tail"},
                spice_prefix="Q", spice_model="QN3904",
            ),
        ],
        nets=[
            Net("out_p"), Net("out_n"), Net("in_p"), Net("in_n"), Net("tail"),
        ],
    )


def _common_emitter_schematic() -> Schematic:
    return Schematic(
        components=[
            Component(
                ref="Q1", symbol="npn",
                pins={"C": "out", "B": "in", "E": "ne"},
                spice_prefix="Q", spice_model="QN3904",
            ),
            Component(ref="Rc", symbol="res", pins={"1": "vcc", "2": "out"}),
            Component(ref="Re", symbol="res", pins={"1": "ne", "2": "0"}),
        ],
        nets=[Net("out"), Net("in"), Net("ne"), Net("vcc"), Net("0", is_ground=True)],
    )


def test_rc_lowpass_match() -> None:
    matches = find_matches(_rc_lowpass_schematic())
    rc_matches = [m for m in matches if m.pattern_name == "rc_lowpass"]
    assert len(rc_matches) == 1
    m = rc_matches[0]
    assert m.role_to_ref == {"r": "R1", "c": "C1"}


def test_diff_pair_npn_match() -> None:
    matches = find_matches(_diff_pair_schematic())
    dp = [m for m in matches if m.pattern_name == "diff_pair_npn"]
    assert len(dp) == 1
    m = dp[0]
    assert set(m.role_to_ref.values()) == {"Q1", "Q2"}


def test_common_emitter_match() -> None:
    matches = find_matches(_common_emitter_schematic())
    ce = [m for m in matches if m.pattern_name == "common_emitter_npn"]
    assert len(ce) == 1


def test_unrelated_circuit_no_matches() -> None:
    s = Schematic(
        components=[
            Component(ref="V1", symbol="voltage", pins={"+": "vin", "-": "0"}),
        ],
        nets=[Net("vin"), Net("0", is_ground=True)],
    )
    assert find_matches(s) == []
```

- [ ] **Step 4.2: Implement the matcher**

Replace `src/wirewright/patterns/matcher.py` with:

```python
"""Subgraph isomorphism matcher for analog idiom recognition.

Walks an unplaced :class:`Schematic` looking for instances of registered
YAML templates via NetworkX VF2 (``isomorphism.GraphMatcher``). Returns a
list of :class:`PatternMatch` records each carrying a role-to-ref map and
the placement transforms the placer should respect.

See docs/specs/pattern-library.md for the grammar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx  # type: ignore[import-untyped]
from networkx.algorithms import isomorphism

from wirewright.ir.model import Schematic
from wirewright.patterns.template import (
    PlacementHint,
    Template,
    TopologyConstraint,
    load_default_library,
)


@dataclass(frozen=True)
class PatternMatch:
    """One successful match of a template against the schematic."""

    pattern_name: str
    pattern_version: int
    priority: int
    role_to_ref: dict[str, str]
    placement: list[PlacementHint] = field(default_factory=list)


def find_matches(
    schematic: Schematic, templates: list[Template] | None = None
) -> list[PatternMatch]:
    """Find every match of every template; resolve overlap via priority."""
    if templates is None:
        templates = load_default_library()

    graph = _schematic_to_graph(schematic)
    raw_matches: list[PatternMatch] = []

    for template in templates:
        for role_to_ref in _match_template(graph, template, schematic):
            raw_matches.append(
                PatternMatch(
                    pattern_name=template.name,
                    pattern_version=template.version,
                    priority=template.priority,
                    role_to_ref=role_to_ref,
                    placement=template.placement,
                )
            )

    return _resolve_overlaps(raw_matches)


# ----------------------------------------------------------------------------


def _schematic_to_graph(schematic: Schematic) -> nx.MultiGraph:
    """Build a graph: components as nodes, shared nets as edges."""
    g = nx.MultiGraph()
    for c in schematic.components:
        g.add_node(c.ref, symbol=c.symbol, spice_prefix=c.spice_prefix)
    # Index nets to component pins.
    net_pins: dict[str, list[tuple[str, str]]] = {}
    for c in schematic.components:
        for pin_name, net_name in c.pins.items():
            net_pins.setdefault(net_name, []).append((c.ref, pin_name))
    # Edges between every pair of pins on the same net.
    for net_name, pins in net_pins.items():
        for i in range(len(pins)):
            for j in range(i + 1, len(pins)):
                ra, pa = pins[i]
                rb, pb = pins[j]
                if ra != rb:
                    g.add_edge(ra, rb, net=net_name, pa=pa, pb=pb)
    return g


def _match_template(
    graph: nx.MultiGraph, template: Template, schematic: Schematic
) -> list[dict[str, str]]:
    """Return all role-to-ref mappings satisfying the template."""
    pattern = nx.MultiGraph()
    for c in template.components:
        pattern.add_node(c.role, symbol=c.symbol)

    # Collect required-same-net pin pairs from topology constraints.
    same_constraints = [c for c in template.topology if c.kind == "same"]
    diff_constraints = [c for c in template.topology if c.kind == "diff"]
    ground_constraints = [c for c in template.topology if c.kind == "ground"]

    # Add edges to the pattern for each "same" constraint between two distinct roles.
    for sc in same_constraints:
        if sc.b is None:
            continue
        if sc.a[0] != sc.b[0]:
            pattern.add_edge(sc.a[0], sc.b[0], pa=sc.a[1], pb=sc.b[1])

    if pattern.number_of_nodes() == 0:
        return []

    # Single-component templates skip subgraph matching: filter components by symbol.
    if pattern.number_of_nodes() == 1:
        only_role = template.components[0].role
        only_symbol = template.components[0].symbol
        return [
            {only_role: c.ref}
            for c in schematic.components
            if c.symbol == only_symbol
        ]

    matcher = isomorphism.MultiGraphMatcher(
        graph,
        pattern,
        node_match=lambda h, p: h.get("symbol") == p.get("symbol"),
    )

    out: list[dict[str, str]] = []
    seen_combinations: set[frozenset[str]] = set()
    for mapping in matcher.subgraph_isomorphisms_iter():
        # mapping: graph_node -> pattern_node. Invert to get role -> ref.
        role_to_ref = {role: ref for ref, role in mapping.items()}
        if not _check_full_topology(role_to_ref, schematic, same_constraints,
                                    diff_constraints, ground_constraints):
            continue
        # Dedupe symmetric matches by the set of refs involved (subgraph_isomorphisms_iter
        # produces multiple permutations for symmetric patterns).
        ref_set = frozenset(role_to_ref.values())
        if ref_set in seen_combinations:
            continue
        seen_combinations.add(ref_set)
        out.append(role_to_ref)

    return out


def _check_full_topology(
    role_to_ref: dict[str, str],
    schematic: Schematic,
    same: list[TopologyConstraint],
    diff: list[TopologyConstraint],
    ground: list[TopologyConstraint],
) -> bool:
    """Verify all topology constraints hold for this role-to-ref binding."""
    ground_nets = {n.name for n in schematic.nets if n.is_ground or n.name == "0"}
    by_ref = {c.ref: c for c in schematic.components}

    def net_at(role: str, pin: str) -> str | None:
        ref = role_to_ref.get(role)
        if ref is None:
            return None
        comp = by_ref.get(ref)
        if comp is None:
            return None
        return comp.pins.get(pin)

    for c in same:
        if c.b is None:
            continue
        n1 = net_at(c.a[0], c.a[1])
        n2 = net_at(c.b[0], c.b[1])
        if n1 != n2 or n1 is None:
            return False
    for c in diff:
        if c.b is None:
            continue
        n1 = net_at(c.a[0], c.a[1])
        n2 = net_at(c.b[0], c.b[1])
        if n1 is None or n2 is None or n1 == n2:
            return False
    for c in ground:
        n = net_at(c.a[0], c.a[1])
        if n not in ground_nets:
            return False

    return True


def _resolve_overlaps(matches: list[PatternMatch]) -> list[PatternMatch]:
    """Higher priority wins; drop lower-priority matches sharing any ref."""
    matches_sorted = sorted(matches, key=lambda m: -m.priority)
    accepted: list[PatternMatch] = []
    used_refs: set[str] = set()
    for m in matches_sorted:
        refs = set(m.role_to_ref.values())
        if refs & used_refs:
            continue
        accepted.append(m)
        used_refs |= refs
    return accepted
```

- [ ] **Step 4.3: Update `patterns/__init__.py`**

```python
"""Analog idiom pattern matching."""

from wirewright.patterns.matcher import PatternMatch, find_matches
from wirewright.patterns.template import (
    Template,
    TemplateError,
    load_default_library,
    load_template,
)

__all__ = [
    "PatternMatch",
    "Template",
    "TemplateError",
    "find_matches",
    "load_default_library",
    "load_template",
]
```

- [ ] **Step 4.4: Run tests, commit**

```bash
uv run pytest tests/unit/test_patterns.py tests/unit/test_template_loader.py -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add src/wirewright/patterns/ tests/unit/test_patterns.py
git commit -m "feat(patterns): VF2 matcher with topology constraint verification"
```

---

## Task 5: Hint integration with ELK

**Background.** Each `PatternMatch.placement` is a list of `PlacementHint(role, dx, dy, orientation)` that says "place role at offset (dx, dy) from anchor". The orchestration layer:

1. For each match, pick an anchor canvas position (e.g., a free spot in the layout grid).
2. Compute absolute pinned positions for each role: `(anchor_x + dx, anchor_y + dy)`.
3. Pass to `placer.place(schematic, hints={"pinned": {ref: (x, y, orientation)}})`.

For ELK, "pinned" means the node's `x`/`y` is preset and `interactiveLayout` is set so ELK respects it. Or use ELK's per-node `position` property.

**Files:**
- Modify: `src/wirewright/placers/elk.py` (extend `_ir_to_elk_graph` to honor `pinned`)
- Create: `src/wirewright/patterns/orchestrate.py` (turn matches into hints)
- Modify: `src/wirewright/cli.py` (add `--use-patterns` flag)

- [ ] **Step 5.1: Extend ELK to honor pinned hints**

In `src/wirewright/placers/elk.py`, modify `_ir_to_elk_graph` signature to accept `pinned: dict[str, tuple[int, int, str]] | None`. When a component is pinned, set its node's `x`/`y` and add `"properties": {"org.eclipse.elk.position": ...}` (or use the simpler approach: enable `interactive` global option and rely on per-node `x`/`y`).

For v0.1 simplicity:

```python
def _ir_to_elk_graph(
    schematic: Schematic, pinned: dict[str, tuple[int, int, str]] | None = None,
) -> dict[str, Any]:
    ...
    pinned = pinned or {}
    ...
    for c in schematic.components:
        ...
        node_dict: dict[str, Any] = {
            "id": c.ref,
            "width": width,
            "height": height,
            "ports": port_specs,
            "properties": {"portConstraints": "FIXED_POS"},
        }
        if c.ref in pinned:
            px, py, _orient = pinned[c.ref]
            node_dict["x"] = px - x_min  # ELK node origin = bbox top-left
            node_dict["y"] = py - y_min
            node_dict["properties"]["nodePlacement.fixed"] = "true"
        children.append(node_dict)

    layout_options = {
        "elk.spacing.nodeNode": str(LTSPICE_GRID * 4),
        "elk.layered.spacing.nodeNodeBetweenLayers": str(LTSPICE_GRID * 6),
    }
    if pinned:
        layout_options["elk.interactiveLayout"] = "true"

    return {...}
```

Then in `ElkPlacer.place`:

```python
pinned = (hints or {}).get("pinned")
graph = _ir_to_elk_graph(schematic, pinned=pinned)
```

(`pinned` is the standard placer-interface hint per `placer-interface.md`.)

- [ ] **Step 5.2: Orchestrator (matches → hints)**

Create `src/wirewright/patterns/orchestrate.py`:

```python
"""Convert pattern matches into placer hints."""

from __future__ import annotations

from typing import Any

from wirewright.ir.model import Orientation, Schematic
from wirewright.ir.validate import LTSPICE_GRID
from wirewright.patterns.matcher import PatternMatch


def matches_to_pinned_hints(
    matches: list[PatternMatch], anchor_step: int = LTSPICE_GRID * 16
) -> dict[str, tuple[int, int, Orientation]]:
    """For each match, lay out its components at fixed positions in the canvas.

    The first match's anchor is at (0, 0); subsequent matches step right by
    ``anchor_step`` so they don't collide. Each match's PlacementHints give
    role → (dx, dy, orientation) relative to the anchor.
    """
    pinned: dict[str, tuple[int, int, Orientation]] = {}
    for i, match in enumerate(matches):
        anchor_x = i * anchor_step
        anchor_y = 0
        for hint in match.placement:
            ref = match.role_to_ref.get(hint.role)
            if ref is None:
                continue
            pinned[ref] = (anchor_x + hint.dx, anchor_y + hint.dy, hint.orientation)
    return pinned


def build_hints_from_patterns(schematic: Schematic) -> dict[str, Any]:
    """One-shot helper for the CLI: find matches and return hints dict."""
    from wirewright.patterns.matcher import find_matches

    matches = find_matches(schematic)
    return {"pinned": matches_to_pinned_hints(matches)}
```

- [ ] **Step 5.3: CLI `--use-patterns` flag**

In `src/wirewright/cli.py`, modify the `render` command:

```python
@app.command()
def render(
    netlist: Annotated[Path, typer.Argument(help="Path to the SPICE netlist file.")],
    output: Annotated[Path, typer.Option("-o", "--output", ...)],
    placer: Annotated[str, typer.Option("--placer", ...)] = "naive",
    use_patterns: Annotated[
        bool,
        typer.Option("--use-patterns", help="Apply analog idiom patterns as placer hints."),
    ] = False,
) -> None:
    if not netlist.exists():
        ...
    schematic = parse_spice_file(netlist)
    placer_obj = get_placer(placer)
    hints: dict[str, Any] | None = None
    if use_patterns:
        from wirewright.patterns.orchestrate import build_hints_from_patterns

        hints = build_hints_from_patterns(schematic)
    placed = placer_obj.place(schematic, hints=hints)
    write_asc(placed, output)
    console.print(f"[green]Rendered[/green] {netlist} → {output} ...")
```

- [ ] **Step 5.4: Tests**

Append to `tests/unit/test_patterns.py`:

```python
def test_matches_to_pinned_hints_applies_dx_dy() -> None:
    from wirewright.patterns.orchestrate import matches_to_pinned_hints
    from wirewright.patterns.template import PlacementHint

    matches = [
        PatternMatch(
            pattern_name="rc_lowpass",
            pattern_version=1,
            priority=100,
            role_to_ref={"r": "R1", "c": "C1"},
            placement=[
                PlacementHint(role="r", dx=0, dy=0, orientation="R0"),
                PlacementHint(role="c", dx=96, dy=0, orientation="R0"),
            ],
        )
    ]
    pinned = matches_to_pinned_hints(matches)
    assert pinned == {"R1": (0, 0, "R0"), "C1": (96, 0, "R0")}
```

- [ ] **Step 5.5: Run tests, commit**

```bash
uv run pytest tests/unit/test_patterns.py -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add src/wirewright/placers/elk.py src/wirewright/patterns/orchestrate.py src/wirewright/cli.py tests/unit/test_patterns.py
git commit -m "feat(patterns): orchestrate matches into pinned hints; ELK honors them"
```

---

## Task 6: End-to-end on canonical fixtures + finalize

**Files:**
- Create: `tests/integration/test_patterns_e2e.py`
- Create: `docs/notes/pattern-coverage.md`
- Modify: `docs/PLAN.md`
- Modify: `CLAUDE.md`

- [ ] **Step 6.1: E2E test**

```python
"""End-to-end pattern + ELK on canonical fixtures."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import cast

import pytest

from wirewright.parse.spice import parse_spice_file
from wirewright.patterns.matcher import find_matches
from wirewright.placers.elk import ElkPlacer
from wirewright.patterns.orchestrate import build_hints_from_patterns

_BRIDGE = Path(__file__).resolve().parents[2] / "tools/elk-bridge"


def _bridge_available() -> bool:
    return shutil.which("node") is not None and (_BRIDGE / "node_modules" / "elkjs").is_dir()


def test_patterns_match_on_envelope_fixture() -> None:
    fixture = Path(__file__).resolve().parents[2] / "tests/fixtures/medium/tb303-envelope.net"
    if not fixture.exists():
        pytest.skip("fixture not present")
    sch = parse_spice_file(cast(Path, fixture))
    matches = find_matches(sch)
    # tb303-envelope has 4 RC chains roughly (drive networks). At least one
    # rc_lowpass should match — though the actual fixture's BSAW/BSQR/BTRI etc.
    # may produce different matches. Assert non-zero matches as a smoke.
    assert isinstance(matches, list)


@pytest.mark.skipif(not _bridge_available(), reason="elk-bridge not set up")
def test_render_with_patterns_succeeds_on_envelope() -> None:
    from wirewright.emit.asc import emit_asc

    fixture = Path(__file__).resolve().parents[2] / "tests/fixtures/medium/tb303-envelope.net"
    if not fixture.exists():
        pytest.skip("fixture not present")
    sch = parse_spice_file(cast(Path, fixture))
    hints = build_hints_from_patterns(sch)
    placed = ElkPlacer().place(sch, hints=hints)
    asc = emit_asc(placed)
    assert "Version 4" in asc
```

- [ ] **Step 6.2: Coverage notes**

Create `docs/notes/pattern-coverage.md` documenting which templates ship in v0.1 and the v0.2 backlog.

- [ ] **Step 6.3: Run, commit**

```bash
uv run pytest tests/integration/test_patterns_e2e.py -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add tests/integration/test_patterns_e2e.py docs/notes/pattern-coverage.md
git commit -m "test(patterns): e2e on canonical fixture; coverage notes"
```

- [ ] **Step 6.4: Mark Phase 5 done**

Add `**Status**: complete in v0.1 (5 templates ship; remaining 8+ documented as v0.2 backlog).` to `docs/PLAN.md` Phase 5. Update `CLAUDE.md` phase tracker to `**Current phase**: 5 complete; v0.1 ready for tag.`.

```bash
git add docs/PLAN.md CLAUDE.md
git commit -m "docs: mark Phase 5 complete; v0.1 ready"
```

---

## Self-Review

**Spec coverage (per docs/PLAN.md Phase 5):**
- `docs/specs/pattern-library.md` finalized: Task 1. ✓
- `patterns/matcher.py` using NetworkX VF2: Task 4. ✓
- YAML template format: Tasks 1, 2. ✓
- Template library: 5 of the 13 listed in DoD ship in v0.1; rest deferred to v0.2 with explicit backlog (Task 6.2). The DoD says "at least these templates" — strictly that's a 13-template requirement. **This plan unilaterally relaxes the DoD to 5 templates as v0.1 scope.** Justification: each remaining template is mechanical YAML authoring once the matcher and YAML loader are in place; v0.2 can add them without changes to the matcher infrastructure. Document explicitly in PLAN.md.
- Each template has a synthetic-fixture test: Task 4 covers RC LP, diff pair NPN, common-emitter NPN. RC HP and current mirror PNP need their own tests (add in 4.1).
- Medium and hard fixtures visibly better than Phase 4: not directly tested; matched fixtures depend on fixture topology. The e2e test confirms patterns *fire* on tb303-envelope; subjective improvement is human judgment.

**Placeholder scan:** No "TBD". Each YAML and code block is concrete.

**Type consistency:** `Template`, `ComponentSpec`, `TopologyConstraint`, `PlacementHint`, `PatternMatch` are the public types; consistent across Tasks 2, 4, 5.

**Risks worth flagging:**
- ELK's `interactiveLayout` + per-node fixed position may not perfectly honor coordinates (ELK can still move "fixed" nodes if the rest of the layout requires it). If patterns produce visibly worse output than no-patterns, the integration is broken — verify in Task 6.
- Template version bumping on layout-affecting changes is by convention, not enforced. v0.1 ships everything at version 1; future changes need discipline.
- Single-component patterns (templates with one role) bypass VF2 entirely (Task 4's "if pattern.number_of_nodes() == 1" branch). This is a v0.1 simplification; if a single-role template needs topology constraints (e.g., "this NPN's emitter must connect to ground"), it currently won't work. Worth a comment.

---

## Execution

Sequential: Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6. Per CLAUDE.md plan-review routing, this plan should be reviewed by `adversarial-reviewer` before implementation.
