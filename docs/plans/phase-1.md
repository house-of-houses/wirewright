# Phase 1 Implementation Plan (rev 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lock down the IR + ASC emitter contract and produce LTspice-correct output for the full common symbol set, so Phase 3+ placers can be developed against a stable round-trip-verified pipeline.

**Architecture:** Six sequential tasks. (1) finish the symbol-geometry audit by fixing the three remaining unverified symbols against their real `.asy` files, including bbox audit and registration-time pin-offset alignment check. (2) strengthen `validate_placed` with true bbox overlap (no per-pin grid check — that invariant is guaranteed by construction once Task 1 lands its registration-time assertion). (3) implement `parse/ltspice_asc.py` using union-find over coordinate equality to recover net membership, with `Opamps/opamp2`-style library-folder prefix handling, lenient flag conflict resolution, and forward-compatibility warnings on unknown line types. (4) wire (1)–(3) into round-trip integration tests covering both the all-flagged-nets case AND the connectivity-isomorphism case where some nets are un-flagged. (5) flip spec statuses from "draft" to "stable in v0.1", document round-trip lossy properties, and bump the phase tracker — honestly worded to reflect that hand-drawn-fixture round-trip is a deferred user deliverable. (6) update `docs/PLAN.md` Phase 1 DoD to match.

**Tech Stack:** Python 3.11, pytest, ruff, mypy, uv. No new runtime dependencies.

**Out of scope (handled separately):**
- Hand-drawn `.asc` reference files for the canonical fixtures (`divider.asc`, `tb303-envelope.asc`, `tb303-vco-integrated.asc`) — author-only deliverables requiring LTspice GUI. Phase 1 DoD line for this is being explicitly deferred in Task 6.
- `emit/asy.py` (custom symbol generation) — explicitly out of scope per the project plan.
- Phase 2 deliverables (Q/M/I/X/.SUBCKT in the SPICE parser) — separate plan.
- Wire endpoint normalization — round-trip relies on emitter's deterministic serialization order; normalizing wires (smaller endpoint first) is a v0.2 spec change.

**Spec sources:**
- `docs/PLAN.md` (high-level phased plan; Phase 1 DoD updated in Task 6)
- `docs/specs/ir.md` (IR contract — invariant 6 strengthened; invariant 7 reworded)
- `docs/specs/asc-emitter.md` (line types, ordering, pin-attachment rules; round-trip lossy-property notes added)
- `docs/specs/netlist-parser.md` (already updated for D/B/E in prior work)
- `docs/specs/placer-interface.md` (uses `validate_placed`, no changes)

**Review compliance:** This plan is rev 2 of the original Phase 1 plan, revised against findings in `docs/plans/phase-1.review.md`. Verdict-blocker findings B1, B2, B3, B5, B6, M2, M3, M4, M5 are addressed in the tasks below; minor findings N1, N2, N3, N5, N7, N8 are folded into the relevant steps; M7 and N9 are documented as known limitations in spec text.

---

## File Structure

| Path | Action | Responsibility |
|------|--------|----------------|
| `src/wirewright/symbols/builtin.py` | Modify | Replace `nmos`/`pmos`/`opamp2` records; add `nmos4`/`pmos4`/`opamp`; drain `UNVERIFIED_SYMBOLS`; add module-load-time assertion that every pin offset is a multiple of `LTSPICE_GRID`. |
| `src/wirewright/symbols/lib_index.py` | Modify | Promote `resolve_asy_path(name)` to a public helper that searches `lib/sym/` plus subfolders (`OpAmps/`). Used by both the audit test and the `.asc` parser. |
| `tests/unit/test_symbols.py` | Modify | Extend `_SPICE_ORDER_BY_SYMBOL` for the 6 new/updated symbols. Add a `test_pin_bboxes_match_asy_file` parametrized audit. Use `resolve_asy_path` from `lib_index`. |
| `tests/unit/test_lib_index.py` | Modify | Add tests for `resolve_asy_path` covering the `OpAmps/` subfolder. |
| `src/wirewright/ir/validate.py` | Modify | Replace approximate origin-overlap with true bbox overlap accounting for orientation. Drop invariant 7 from the runtime check (now guaranteed by construction). |
| `tests/unit/test_ir.py` | Modify | Tests for the strengthened bbox-overlap invariant. |
| `src/wirewright/parse/ltspice_asc.py` | Rewrite | Parse `.asc` text → IR `Schematic` via line tokenization + union-find net recovery. Strip library folder prefix (e.g. `Opamps/opamp2` → `opamp2`) before symbol lookup. Lenient flag conflict (warn, first-name-wins). Wrap `Wire(...)` to re-raise as `AscParseError` on non-axis-aligned input. Warn on unknown SYMATTR keys / unknown line types. |
| `tests/unit/test_ltspice_asc.py` | Create | Tests for the `.asc` parser using inline string fixtures: empty file, version header, WIRE/FLAG/SYMBOL/TEXT, library-folder prefix, conflict warning, non-axis-aligned wire error. |
| `tests/integration/test_round_trip.py` | Create | (a) Round-trip of fully-flagged Schematic; (b) Round-trip with un-flagged interior net asserted via connectivity isomorphism. |
| `docs/specs/ir.md` | Modify | Status: draft → stable in v0.1. Reword invariant 7. Document `Net.is_power` parser-side limitation and `Schematic.nets` ordering instability. Resolve both open questions consistently (defer to ADR-0002). |
| `docs/specs/asc-emitter.md` | Modify | Status: draft → stable in v0.1. Document round-trip lossy properties (standard `spice_prefix`, `Net.is_power`, `Schematic.nets` ordering). |
| `docs/PLAN.md` | Modify | Phase 1 DoD: split "ASC emitter passes round-trip on all three fixtures" bullet into "(a) round-trip on synthetic data" (in scope, Task 4) and "(b) round-trip on hand-drawn `.asc` fixtures" (deferred — gated on user authoring). |
| `CLAUDE.md` | Modify | Phase tracker line: "Phase 1 implementation complete; hand-drawn fixture round-trip pending". |

---

## Task 1: Verified symbol geometry — fix the three unverified symbols and harden the audit

**Background.** The audit test in `tests/unit/test_symbols.py::test_pin_offsets_match_asy_file` is parametrized over symbols listed in `_SPICE_ORDER_BY_SYMBOL`. Three symbols are flagged in `UNVERIFIED_SYMBOLS`: `nmos`, `pmos`, `opamp2`. `opamp` is missing entirely. We also need `nmos4` and `pmos4` for the 4-pin SPICE M card variant (Phase 2 parser will pick the right one based on whether the SPICE node count is 3 or 4).

Verified offsets read from `~/Library/Application Support/LTspice/lib/sym/`:

```
nmos.asy:    PIN 48 0 → "D" (1); PIN 0 80 → "G" (2); PIN 48 96 → "S" (3). bbox (0, 0, 48, 96).
nmos4.asy:   adds PIN 48 48 → "B" (4). bbox (0, 0, 48, 96).
pmos.asy:    same coords as nmos.
pmos4.asy:   same coords as nmos4.
OpAmps/opamp.asy:   PIN -32 48 → "invin" (1); PIN -32 80 → "noninvin" (2); PIN 32 64 → "out" (3). bbox (-32, 32, 32, 96).
OpAmps/opamp2.asy:  PIN -32 80 → "In+" (1); PIN -32 48 → "In-" (2); PIN 0 32 → "V+" (3); PIN 0 96 → "V-" (4); PIN 32 64 → "OUT" (5). bbox (-32, 32, 32, 96).
```

Confirmed by greppable check: no callers in `src/` or `tests/` use the OLD pin name conventions `+`/`-`/`OUT`/`V+`/`V-` for opamp2. Pin-name change is safe.

**Files:**
- Modify: `src/wirewright/symbols/builtin.py`
- Modify: `src/wirewright/symbols/lib_index.py`
- Modify: `tests/unit/test_symbols.py`
- Modify: `tests/unit/test_lib_index.py`

- [ ] **Step 1.1: Promote `resolve_asy_path` to `lib_index.py`**

Append to `src/wirewright/symbols/lib_index.py`:

```python
_SUBFOLDERS_TO_SEARCH: tuple[str, ...] = ("", "OpAmps", "Comparators", "Digital")


def resolve_asy_path(name: str, lib: Path | None = None) -> Path | None:
    """Locate the ``.asy`` file for a symbol name within the LTspice library.

    Tries the lib root first, then known subfolders (``OpAmps/``, ``Comparators/``,
    ``Digital/``). Accepts ``name`` with or without a leading folder prefix
    (e.g. ``"opamp2"`` and ``"OpAmps/opamp2"`` both resolve to the same path).

    Returns None when the library is not found or the symbol isn't there.
    """
    if lib is None:
        lib = default_ltspice_lib_path()
    if lib is None:
        return None
    bare = name.split("/")[-1]
    for folder in _SUBFOLDERS_TO_SEARCH:
        candidate = (lib / folder / f"{bare}.asy") if folder else (lib / f"{bare}.asy")
        if candidate.is_file():
            return candidate
    return None
```

- [ ] **Step 1.2: Test `resolve_asy_path`**

Append to `tests/unit/test_lib_index.py`:

```python
def test_resolve_asy_path_finds_root_symbol() -> None:
    from wirewright.symbols.lib_index import resolve_asy_path

    p = resolve_asy_path("res")
    if p is None:
        pytest.skip("LTspice library not found")
    assert p.name == "res.asy"


def test_resolve_asy_path_finds_subfolder_symbol() -> None:
    from wirewright.symbols.lib_index import resolve_asy_path

    p = resolve_asy_path("opamp2")
    if p is None:
        pytest.skip("LTspice library not found or opamp2 missing")
    assert p.parent.name == "OpAmps"


def test_resolve_asy_path_accepts_prefixed_name() -> None:
    from wirewright.symbols.lib_index import resolve_asy_path

    bare = resolve_asy_path("opamp2")
    prefixed = resolve_asy_path("OpAmps/opamp2")
    if bare is None:
        pytest.skip("LTspice library not found")
    assert bare == prefixed


def test_resolve_asy_path_returns_none_for_unknown() -> None:
    from wirewright.symbols.lib_index import resolve_asy_path

    assert resolve_asy_path("does_not_exist_anywhere") is None
```

Run: `uv run pytest tests/unit/test_lib_index.py -v`
Expected: all pass on a machine with the LTspice install; the LTspice-dependent ones skip on machines without it.

- [ ] **Step 1.3: Update audit map and add bbox audit (failing tests)**

Edit `tests/unit/test_symbols.py`. Replace the `_SPICE_ORDER_BY_SYMBOL` dict (around line 31) with:

```python
_SPICE_ORDER_BY_SYMBOL: dict[str, dict[str, int]] = {
    "res": {"1": 1, "2": 2},
    "ind": {"1": 1, "2": 2},
    "cap": {"1": 1, "2": 2},
    "polcap": {"1": 1, "2": 2},
    "diode": {"A": 1, "K": 2},
    "npn": {"C": 1, "B": 2, "E": 3},
    "pnp": {"C": 1, "B": 2, "E": 3},
    "voltage": {"+": 1, "-": 2},
    "current": {"+": 1, "-": 2},
    "bv": {"+": 1, "-": 2},
    "e": {"+": 1, "-": 2, "P": 3, "N": 4},
    "nmos": {"D": 1, "G": 2, "S": 3},
    "nmos4": {"D": 1, "G": 2, "S": 3, "B": 4},
    "pmos": {"D": 1, "G": 2, "S": 3},
    "pmos4": {"D": 1, "G": 2, "S": 3, "B": 4},
    "opamp": {"invin": 1, "noninvin": 2, "out": 3},
    "opamp2": {"In+": 1, "In-": 2, "V+": 3, "V-": 4, "OUT": 5},
}
```

Replace the existing `_resolve_asy_path` helper (if present from rev 1) with a thin wrapper around `lib_index.resolve_asy_path`. Replace `test_pin_offsets_match_asy_file` body so the path lookup uses the resolver:

```python
@pytest.mark.parametrize("name", sorted(_SPICE_ORDER_BY_SYMBOL))
def test_pin_offsets_match_asy_file(name: str) -> None:
    """Each verified symbol's pin offsets match the real LTspice .asy."""
    if name in UNVERIFIED_SYMBOLS:
        pytest.skip(f"{name} is flagged unverified in builtin.py")
    from wirewright.symbols.lib_index import (
        parse_asy_pins_by_spice_order,
        resolve_asy_path,
    )

    asy_path = resolve_asy_path(name)
    if asy_path is None:
        pytest.skip(f"{name}.asy not present in this LTspice install")

    asy_by_order = parse_asy_pins_by_spice_order(asy_path)
    expected = {
        ir_name: asy_by_order[order]
        for ir_name, order in _SPICE_ORDER_BY_SYMBOL[name].items()
    }
    assert symbol_geometry(name).pins == expected
```

Add a parametrized bbox audit immediately after:

```python
@pytest.mark.parametrize("name", sorted(_SPICE_ORDER_BY_SYMBOL))
def test_pin_bboxes_match_asy_file(name: str) -> None:
    """Each verified symbol's bbox matches what parse_asy_file would extract."""
    if name in UNVERIFIED_SYMBOLS:
        pytest.skip(f"{name} is flagged unverified in builtin.py")
    from wirewright.symbols.lib_index import parse_asy_file, resolve_asy_path

    asy_path = resolve_asy_path(name)
    if asy_path is None:
        pytest.skip(f"{name}.asy not present in this LTspice install")
    expected = parse_asy_file(asy_path).bbox
    assert symbol_geometry(name).bbox == expected
```

- [ ] **Step 1.4: Run failing tests**

Run: `uv run pytest tests/unit/test_symbols.py -v`
Expected: failures on `pin_offsets_match` for `nmos`/`pmos`/`opamp2` (still in UNVERIFIED → skip, but new entries `nmos4`/`pmos4`/`opamp` raise KeyError because they're not registered yet); the bbox audit fails on the same set with KeyError.

- [ ] **Step 1.5: Replace `nmos`/`pmos`/`opamp2`; add `nmos4`/`pmos4`/`opamp`; drain UNVERIFIED_SYMBOLS; add registration-time pin-grid assertion**

Edit `src/wirewright/symbols/builtin.py`. Replace the records under "Best-effort approximations" plus the `UNVERIFIED_SYMBOLS` constant with the verified set:

```python
# Verified against the real LTspice .asy library.
_NMOS = SymbolGeometry(
    name="nmos",
    pins={"D": (48, 0), "G": (0, 80), "S": (48, 96)},
    bbox=(0, 0, 48, 96),
)

_NMOS4 = SymbolGeometry(
    name="nmos4",
    pins={"D": (48, 0), "G": (0, 80), "S": (48, 96), "B": (48, 48)},
    bbox=(0, 0, 48, 96),
)

_PMOS = SymbolGeometry(
    name="pmos",
    pins={"D": (48, 0), "G": (0, 80), "S": (48, 96)},
    bbox=(0, 0, 48, 96),
)

_PMOS4 = SymbolGeometry(
    name="pmos4",
    pins={"D": (48, 0), "G": (0, 80), "S": (48, 96), "B": (48, 48)},
    bbox=(0, 0, 48, 96),
)

_OPAMP = SymbolGeometry(
    name="opamp",
    pins={"invin": (-32, 48), "noninvin": (-32, 80), "out": (32, 64)},
    bbox=(-32, 32, 32, 96),
)

_OPAMP2 = SymbolGeometry(
    name="opamp2",
    pins={
        "In+": (-32, 80),
        "In-": (-32, 48),
        "V+": (0, 32),
        "V-": (0, 96),
        "OUT": (32, 64),
    },
    bbox=(-32, 32, 32, 96),
)


UNVERIFIED_SYMBOLS: frozenset[str] = frozenset()
```

Update `_REGISTRY` to include the new entries:

```python
_REGISTRY: dict[str, SymbolGeometry] = {
    g.name: g
    for g in [
        _RES,
        _IND,
        _CAP,
        _POLCAP,
        _DIODE,
        _NPN,
        _PNP,
        _VOLTAGE,
        _CURRENT,
        _BV,
        _E,
        _NMOS,
        _NMOS4,
        _PMOS,
        _PMOS4,
        _OPAMP,
        _OPAMP2,
    ]
}
```

Append a registration-time check at module load (after `_REGISTRY`):

```python
def _assert_pin_offsets_grid_aligned() -> None:
    """Module-load invariant: every registered pin offset is on the grid.

    This is invariant 7 from docs/specs/ir.md, enforced by construction.
    Wired here so a new symbol record with off-grid pins fails import,
    not at runtime in the placer.
    """
    from wirewright.ir.validate import LTSPICE_GRID

    for geo in _REGISTRY.values():
        for pin_name, (dx, dy) in geo.pins.items():
            if dx % LTSPICE_GRID != 0 or dy % LTSPICE_GRID != 0:
                raise AssertionError(
                    f"Symbol {geo.name!r} pin {pin_name!r} offset ({dx}, {dy}) "
                    f"not aligned to LTspice grid ({LTSPICE_GRID})"
                )


_assert_pin_offsets_grid_aligned()
```

Update the module docstring: replace the paragraph mentioning `UNVERIFIED_SYMBOLS` with: "All registered symbols are verified against the real LTspice `.asy` files via the audit tests in `tests/unit/test_symbols.py`. Pin offsets are asserted to be multiples of `LTSPICE_GRID` at module load — see ``_assert_pin_offsets_grid_aligned``."

- [ ] **Step 1.6: Run audit tests, expect all pass on local machine**

Run: `uv run pytest tests/unit/test_symbols.py tests/unit/test_lib_index.py -v`
Expected: all parametrized audits PASS (or SKIP on CI without LTspice). Total ≈ 60+ tests in `test_symbols.py` (existing 22 + 17 pin audits + 17 bbox audits = 56).

- [ ] **Step 1.7: Run full suite**

Run: `uv run pytest`
Expected: all tests pass.

- [ ] **Step 1.8: Lint, format, type-check**

Run: `uv run ruff format && uv run ruff check && uv run mypy src`
Expected: all green.

- [ ] **Step 1.9: Commit**

```bash
git add src/wirewright/symbols/builtin.py src/wirewright/symbols/lib_index.py tests/unit/test_symbols.py tests/unit/test_lib_index.py
git commit -m "feat(symbols): verify nmos/pmos/opamp/opamp2 vs .asy; add bbox+grid audits"
```

---

## Task 2: Strengthen `validate_placed` with true bbox overlap (no per-pin grid check)

**Background.** `docs/specs/ir.md` invariant 6 ("no two component bounding boxes overlap") is currently a placeholder check on shared origins only. Invariant 7 ("every pin's absolute position lies on the grid") is, on close inspection, *guaranteed by construction* once invariant 5 (component on grid) and the registration-time pin-grid assertion (Task 1.5) hold — `(c.x + dx) % 16 == 0` is automatic because both terms are multiples of 16, and `rotate_offset` is a sign-flip / coord-swap that preserves divisibility.

We therefore strengthen invariant 6 with a real bbox-overlap check and **drop the runtime check for invariant 7**. The IR spec is updated in Task 5 to clarify invariant 7's "by construction" status.

**Files:**
- Modify: `src/wirewright/ir/validate.py`
- Modify: `tests/unit/test_ir.py`

- [ ] **Step 2.1: Write failing tests for bbox overlap**

Append to `tests/unit/test_ir.py`:

```python
def test_validate_placed_rejects_bbox_overlap() -> None:
    # Two resistors stacked at the same column, vertically overlapping.
    # Each res bbox is (0, 16, 32, 96). Origins (64, 64) and (64, 80) →
    # bboxes (64, 80, 96, 160) and (64, 96, 96, 176) → overlap.
    s = Schematic(
        components=[
            Component(ref="R1", symbol="res", pins={"1": "a", "2": "b"}, x=64, y=64),
            Component(ref="R2", symbol="res", pins={"1": "b", "2": "0"}, x=64, y=80),
        ],
        nets=[Net("a"), Net("b"), Net("0", is_ground=True)],
    )
    with pytest.raises(ValidationError, match="overlap"):
        validate_placed(s)


def test_validate_placed_accepts_adjacent_bboxes() -> None:
    # Touching but not overlapping: origins horizontally separated by 64,
    # res bbox is 32 wide → bboxes don't overlap.
    s = Schematic(
        components=[
            Component(ref="R1", symbol="res", pins={"1": "a", "2": "b"}, x=64, y=64),
            Component(ref="R2", symbol="res", pins={"1": "b", "2": "0"}, x=128, y=64),
        ],
        nets=[Net("a"), Net("b"), Net("0", is_ground=True)],
    )
    validate_placed(s)  # no raise


def test_validate_placed_handles_rotated_bbox_correctly() -> None:
    # res rotated R90: bbox under R0 is (0, 16, 32, 96). Rotated about the
    # origin, the new AABB is (-96, 0, -16, 32) (negative x extends left).
    # Place R1 at (200, 200) R90 → bbox (104, 200, 184, 232).
    # Place R2 at (160, 200) R0 → bbox (160, 216, 192, 296).
    # x ranges (104..184) and (160..192) overlap; y ranges (200..232) and
    # (216..296) overlap → overall overlap.
    s = Schematic(
        components=[
            Component(ref="R1", symbol="res", pins={"1": "a", "2": "b"},
                      x=200, y=200, orientation="R90"),
            Component(ref="R2", symbol="res", pins={"1": "b", "2": "0"},
                      x=160, y=200, orientation="R0"),
        ],
        nets=[Net("a"), Net("b"), Net("0", is_ground=True)],
    )
    with pytest.raises(ValidationError, match="overlap"):
        validate_placed(s)
```

(Imports `pytest`, `Component`, `Net`, `Schematic`, `ValidationError`, `validate_placed` should already be at the top of the file; add any missing.)

- [ ] **Step 2.2: Run tests, verify failures**

Run: `uv run pytest tests/unit/test_ir.py -v -k "bbox or adjacent or rotated"`
Expected: 2 FAIL (bbox-overlap tests), 1 PASS (adjacent vacuous).

- [ ] **Step 2.3: Replace `_check_no_overlap` with bbox overlap detection; remove dead invariant**

Edit `src/wirewright/ir/validate.py`. Replace `_check_no_overlap` entirely with:

```python
def _check_no_overlap(s: Schematic) -> None:
    """Reject any pair of components whose oriented bounding boxes overlap."""
    from wirewright.symbols.builtin import rotate_offset, symbol_geometry

    placed: list[tuple[str, tuple[int, int, int, int]]] = []
    for c in s.components:
        if c.x is None or c.y is None:
            continue
        try:
            geo = symbol_geometry(c.symbol)
        except KeyError:
            continue  # unknown symbol — caught elsewhere
        x1, y1, x2, y2 = geo.bbox
        # Rotate the four bbox corners around the symbol origin and re-min/re-max
        # to handle non-R0 orientations (including the four mirror variants).
        corners = [
            rotate_offset((x1, y1), c.orientation),
            rotate_offset((x2, y1), c.orientation),
            rotate_offset((x1, y2), c.orientation),
            rotate_offset((x2, y2), c.orientation),
        ]
        rxs = [p[0] for p in corners]
        rys = [p[1] for p in corners]
        bbox = (c.x + min(rxs), c.y + min(rys), c.x + max(rxs), c.y + max(rys))
        placed.append((c.ref, bbox))

    for i, (ref_a, a) in enumerate(placed):
        for ref_b, b in placed[i + 1 :]:
            # Touching edges are not overlap; strict less-than.
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                raise ValidationError(
                    f"Components {ref_a!r} and {ref_b!r} bounding boxes overlap"
                )
```

Leave `validate_placed` itself unchanged (it already calls `_check_no_overlap`). Do **not** add a `_check_pin_grid_alignment` — that invariant is enforced at symbol-registration time (Task 1.5).

- [ ] **Step 2.4: Run tests; expect all pass**

Run: `uv run pytest tests/unit/test_ir.py -v`
Expected: all pass.

- [ ] **Step 2.5: Run full suite to catch placer regressions**

Run: `uv run pytest`
Expected: all pass. The naive placer's `TestAnyPlacer::test_no_overlap[naive]` now exercises the strengthened check; passes because `naive` spaces components by 192 IR units.

- [ ] **Step 2.6: Lint, format, type-check**

Run: `uv run ruff format && uv run ruff check && uv run mypy src`

- [ ] **Step 2.7: Commit**

```bash
git add src/wirewright/ir/validate.py tests/unit/test_ir.py
git commit -m "feat(ir): strengthen validate_placed bbox-overlap with orientation handling"
```

---

## Task 3: Implement `parse/ltspice_asc.py`

**Background.** The `.asc` format has no explicit net declarations. Two points are on the same net iff joined by a path of `WIRE` segments and/or by being colocated. A `FLAG` at `(x, y)` labels the net at that point. A `SYMBOL` placed at origin `(cx, cy)` with orientation `o` exposes pins at `absolute_pin_position(...)`.

**Algorithm:**

1. Tokenize lines. Recognize: `Version 4`, `SHEET 1 W H`, `WIRE x1 y1 x2 y2`, `FLAG x y name`, `SYMBOL libname x y orientation`, `SYMATTR Key Value`, `TEXT x y align size body`. Unknown line types emit a `warnings.warn(...)` for forward compatibility (per CLAUDE.md "fail loudly" — but this is recoverable, so warn rather than raise).
2. Build a coordinate union-find. Atoms: every wire endpoint, every flag position, every absolute pin position of every placed symbol. For each WIRE, also union every grid-aligned point along the segment so a wire passing through a pin connects to the pin without needing the wire endpoint to land exactly on the pin.
3. After unioning: each connected component is a net. Pick the net name from any colocated `FLAG`; if multiple FLAGs in one component disagree, **first-name-wins with `warnings.warn`** (LTspice tolerates this; we log and proceed). For un-flagged components, generate synthetic names `n1`, `n2`, ... in deterministic order (sorted by min-coordinate root for stability).
4. Resolve `SYMBOL` libname: strip leading folder prefix (`Opamps/opamp2` → `opamp2`) before registry lookup. Preserve the full prefixed form on `Component.symbol` for round-trip fidelity.
5. Wrap `Wire(...)` construction in try/except: re-raise as `AscParseError` with line context if `__post_init__` rejects (non-axis-aligned).
6. `TEXT` lines: bodies starting with `!` are SPICE directives → `Schematic.directives`. Bodies starting with `;` are comments → drop. Other content silently dropped (no IR field for it in v0.1).
7. Unknown `SYMATTR` keys (not in `InstName`/`Value`/`SpiceModel`/`Prefix`): `warnings.warn` and continue.

**Files:**
- Rewrite: `src/wirewright/parse/ltspice_asc.py`
- Create: `tests/unit/test_ltspice_asc.py`

- [ ] **Step 3.1: Write failing tests for empty + version handling**

Create `tests/unit/test_ltspice_asc.py`:

```python
"""Tests for the LTspice .asc parser."""

from __future__ import annotations

import warnings

import pytest

from wirewright.parse.ltspice_asc import AscParseError, parse_asc_text


def test_empty_asc_returns_empty_schematic() -> None:
    sch = parse_asc_text("Version 4\nSHEET 1 880 680\n")
    assert sch.components == []
    assert sch.nets == []
    assert sch.wires == []
    assert sch.flags == []


def test_missing_version_header_raises() -> None:
    with pytest.raises(AscParseError, match="Version"):
        parse_asc_text("SHEET 1 880 680\n")
```

Run: `uv run pytest tests/unit/test_ltspice_asc.py -v`
Expected: ImportError (parser stubbed); both tests fail.

- [ ] **Step 3.2: Implement minimal parser**

Replace `src/wirewright/parse/ltspice_asc.py` with:

```python
"""LTspice .asc file parser. See docs/specs/asc-emitter.md for the inverse.

Round-trip lossy properties (documented; tested in tests/integration/test_round_trip.py):
- ``Net.is_power`` is reset to False on every parsed net (no .asc convention).
- ``Schematic.nets`` ordering is not preserved across round-trip.
- ``Component.spice_prefix`` for standard prefixes is dropped (emitter only writes
  non-standard prefixes; see emit/asc.py:65).
- Free TEXT comments (``;``-prefixed) are dropped (no IR field in v0.1).
"""

from __future__ import annotations

import warnings
from collections import defaultdict
from pathlib import Path
from typing import cast, get_args

from wirewright.ir.model import Component, Flag, Net, Orientation, Schematic, Wire
from wirewright.symbols.builtin import absolute_pin_position, symbol_geometry


class AscParseError(Exception):
    """Raised when a .asc file cannot be parsed."""


_VALID_ORIENTATIONS: frozenset[str] = frozenset(get_args(Orientation))


def parse_asc_file(path: str | Path) -> Schematic:
    """Parse a .asc file into IR with positions populated."""
    return parse_asc_text(Path(path).read_text())


def parse_asc_text(text: str) -> Schematic:
    """Parse .asc text into IR with positions populated."""
    lines = text.splitlines()
    if not lines or not lines[0].startswith("Version "):
        raise AscParseError("missing 'Version N' header on first line")

    components: list[Component] = []
    wires: list[Wire] = []
    flags: list[Flag] = []
    directives: list[str] = []
    current: Component | None = None

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("Version") or line.startswith("SHEET"):
            continue

        tokens = line.split()
        kind = tokens[0]

        if kind == "WIRE":
            if len(tokens) != 5:
                raise AscParseError(f"line {line_no}: malformed WIRE: {line!r}")
            try:
                wire = Wire(int(tokens[1]), int(tokens[2]), int(tokens[3]), int(tokens[4]))
            except ValueError as e:
                raise AscParseError(f"line {line_no}: invalid WIRE: {e}") from e
            wires.append(wire)

        elif kind == "FLAG":
            if len(tokens) != 4:
                raise AscParseError(f"line {line_no}: malformed FLAG: {line!r}")
            flags.append(Flag(int(tokens[1]), int(tokens[2]), tokens[3]))

        elif kind == "SYMBOL":
            if len(tokens) != 5:
                raise AscParseError(f"line {line_no}: malformed SYMBOL: {line!r}")
            symbol, sx, sy, orient = tokens[1], int(tokens[2]), int(tokens[3]), tokens[4]
            if orient not in _VALID_ORIENTATIONS:
                raise AscParseError(f"line {line_no}: unknown orientation {orient!r}")
            current = Component(
                ref="",
                symbol=symbol,
                pins={},
                x=sx,
                y=sy,
                orientation=cast(Orientation, orient),
            )
            components.append(current)

        elif kind == "SYMATTR":
            if current is None:
                raise AscParseError(f"line {line_no}: SYMATTR without preceding SYMBOL")
            if len(tokens) < 3:
                raise AscParseError(f"line {line_no}: malformed SYMATTR: {line!r}")
            key = tokens[1]
            value = " ".join(tokens[2:])
            if key == "InstName":
                current.ref = value
            elif key == "Value":
                current.value = value
            elif key == "SpiceModel":
                current.spice_model = value
            elif key == "Prefix":
                current.spice_prefix = value
            else:
                warnings.warn(
                    f"line {line_no}: unknown SYMATTR key {key!r} dropped",
                    stacklevel=2,
                )

        elif kind == "TEXT":
            if len(tokens) < 6:
                continue
            body = " ".join(tokens[5:])
            if body.startswith("!"):
                directives.append(body[1:])
            # Comments and free text dropped silently (no IR field in v0.1).

        else:
            warnings.warn(
                f"line {line_no}: unknown line type {kind!r} dropped",
                stacklevel=2,
            )

    sch = Schematic(
        components=components,
        nets=[],
        wires=wires,
        flags=flags,
        directives=directives,
    )
    _recover_nets(sch)
    return sch
```

Append the union-find and net-recovery code below the function:

```python
class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[tuple[int, int], tuple[int, int]] = {}

    def find(self, p: tuple[int, int]) -> tuple[int, int]:
        if p not in self._parent:
            self._parent[p] = p
            return p
        root = p
        while self._parent[root] != root:
            root = self._parent[root]
        cur = p
        while self._parent[cur] != root:
            self._parent[cur], cur = root, self._parent[cur]
        return root

    def union(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


_LATTICE_LIMIT = 1024


def _wire_lattice_points(w: Wire) -> list[tuple[int, int]]:
    """All grid-aligned points on the wire segment, including both endpoints."""
    from wirewright.ir.validate import LTSPICE_GRID

    pts: list[tuple[int, int]] = []
    if w.x1 == w.x2:
        ys = sorted([w.y1, w.y2])
        y = ys[0]
        while y <= ys[1]:
            pts.append((w.x1, y))
            y += LTSPICE_GRID
            if len(pts) > _LATTICE_LIMIT:
                raise AscParseError(
                    f"wire {w} spans more than {_LATTICE_LIMIT} grid units"
                )
    else:  # y1 == y2 (axis-aligned by Wire.__post_init__)
        xs = sorted([w.x1, w.x2])
        x = xs[0]
        while x <= xs[1]:
            pts.append((x, w.y1))
            x += LTSPICE_GRID
            if len(pts) > _LATTICE_LIMIT:
                raise AscParseError(
                    f"wire {w} spans more than {_LATTICE_LIMIT} grid units"
                )
    return pts


def _strip_lib_folder(symbol: str) -> str:
    """Remove leading library folder prefix (e.g. 'Opamps/opamp2' → 'opamp2')."""
    return symbol.rsplit("/", 1)[-1]


def _recover_nets(sch: Schematic) -> None:
    """Populate sch.components[*].pins and sch.nets via coordinate union-find."""
    uf = _UnionFind()

    component_pins: list[tuple[Component, str, tuple[int, int]]] = []
    for c in sch.components:
        if c.x is None or c.y is None:
            continue
        try:
            geo = symbol_geometry(_strip_lib_folder(c.symbol))
        except KeyError as e:
            raise AscParseError(
                f"Component {c.ref!r} uses unknown symbol {c.symbol!r}"
            ) from e
        for pin_name in geo.pins:
            pos = absolute_pin_position(
                (c.x, c.y), _strip_lib_folder(c.symbol), pin_name, c.orientation
            )
            uf.find(pos)
            component_pins.append((c, pin_name, pos))

    for w in sch.wires:
        pts = _wire_lattice_points(w)
        for q in pts[1:]:
            uf.union(pts[0], q)

    for fl in sch.flags:
        uf.find((fl.x, fl.y))

    name_for_root: dict[tuple[int, int], str] = {}
    for fl in sch.flags:
        root = uf.find((fl.x, fl.y))
        existing = name_for_root.get(root)
        if existing is None:
            name_for_root[root] = fl.net
        elif existing != fl.net:
            warnings.warn(
                f"net at {(fl.x, fl.y)} flagged both {existing!r} and {fl.net!r}; "
                f"keeping {existing!r} (first-flag-wins; LTspice-tolerant)",
                stacklevel=2,
            )

    synthetic_counter = 0
    root_to_synthetic: dict[tuple[int, int], str] = {}

    def name_for(pos: tuple[int, int]) -> str:
        nonlocal synthetic_counter
        root = uf.find(pos)
        if root in name_for_root:
            return name_for_root[root]
        if root not in root_to_synthetic:
            synthetic_counter += 1
            root_to_synthetic[root] = f"n{synthetic_counter}"
        return root_to_synthetic[root]

    for c, pin_name, pos in component_pins:
        c.pins[pin_name] = name_for(pos)

    seen: dict[str, Net] = {}
    for c in sch.components:
        for net_name in c.pins.values():
            if net_name in seen:
                continue
            seen[net_name] = Net(name=net_name, is_ground=net_name == "0")
    sch.nets = list(seen.values())
```

Run: `uv run pytest tests/unit/test_ltspice_asc.py -v`
Expected: 2 pass.

- [ ] **Step 3.3: Add tests for the full line-type set**

Append to `tests/unit/test_ltspice_asc.py`:

```python
_CLEAN_TWO_RESISTOR_ASC = """\
Version 4
SHEET 1 416 320
WIRE 80 80 80 48
WIRE 80 48 272 48
WIRE 272 48 272 80
FLAG 80 160 vin
FLAG 80 48 n1
FLAG 272 160 0
SYMBOL res 64 64 R0
SYMATTR InstName R1
SYMATTR Value 10k
SYMBOL res 256 64 R0
SYMATTR InstName R2
SYMATTR Value 10k
TEXT 128 240 Left 2 !.tran 1m
"""


def test_clean_asc_recovers_components() -> None:
    sch = parse_asc_text(_CLEAN_TWO_RESISTOR_ASC)
    refs = {c.ref for c in sch.components}
    assert refs == {"R1", "R2"}
    r1 = sch.component_by_ref("R1")
    assert r1.symbol == "res"
    assert r1.value == "10k"
    assert (r1.x, r1.y, r1.orientation) == (64, 64, "R0")


def test_clean_asc_recovers_wires() -> None:
    sch = parse_asc_text(_CLEAN_TWO_RESISTOR_ASC)
    assert {(w.x1, w.y1, w.x2, w.y2) for w in sch.wires} == {
        (80, 80, 80, 48),
        (80, 48, 272, 48),
        (272, 48, 272, 80),
    }


def test_clean_asc_recovers_flags() -> None:
    sch = parse_asc_text(_CLEAN_TWO_RESISTOR_ASC)
    assert {(f.x, f.y, f.net) for f in sch.flags} == {
        (80, 160, "vin"),
        (80, 48, "n1"),
        (272, 160, "0"),
    }


def test_clean_asc_recovers_directives() -> None:
    sch = parse_asc_text(_CLEAN_TWO_RESISTOR_ASC)
    assert sch.directives == [".tran 1m"]


def test_clean_asc_recovers_nets_via_connectivity() -> None:
    sch = parse_asc_text(_CLEAN_TWO_RESISTOR_ASC)
    assert {n.name for n in sch.nets} == {"vin", "n1", "0"}
    r1 = sch.component_by_ref("R1")
    r2 = sch.component_by_ref("R2")
    assert r1.pins == {"1": "n1", "2": "vin"}
    assert r2.pins == {"1": "n1", "2": "0"}


def test_non_axis_aligned_wire_raises_with_line_context() -> None:
    bad = "Version 4\nSHEET 1 880 680\nWIRE 80 80 100 100\n"
    with pytest.raises(AscParseError, match="line 3"):
        parse_asc_text(bad)


def test_unknown_symattr_emits_warning() -> None:
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "SYMBOL res 64 64 R0\nSYMATTR InstName R1\nSYMATTR FooBar baz\n"
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        parse_asc_text(asc)
        assert any("FooBar" in str(rec.message) for rec in w)


def test_unknown_line_type_emits_warning() -> None:
    asc = "Version 4\nSHEET 1 880 680\nBUSTAP 0 0 0 16\n"
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        parse_asc_text(asc)
        assert any("BUSTAP" in str(rec.message) for rec in w)


def test_lib_folder_prefix_stripped_for_registry_lookup() -> None:
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "FLAG 0 64 inv\nFLAG 0 96 noninv\nFLAG 64 80 out\n"
        "SYMBOL Opamps/opamp 32 16 R0\nSYMATTR InstName U1\n"
    )
    sch = parse_asc_text(asc)
    u1 = sch.component_by_ref("U1")
    assert u1.symbol == "Opamps/opamp"  # full path preserved
    # Pin connectivity recovered via _strip_lib_folder lookup.
    assert "invin" in u1.pins
    assert "noninvin" in u1.pins
    assert "out" in u1.pins


def test_conflicting_flag_names_warn_first_wins() -> None:
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "WIRE 80 80 80 96\n"
        "FLAG 80 80 alpha\n"
        "FLAG 80 96 beta\n"
        "SYMBOL res 64 64 R0\nSYMATTR InstName R1\nSYMATTR Value 10k\n"
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sch = parse_asc_text(asc)
    # First flag (alpha at (80, 80)) wins for the connected component.
    r1 = sch.component_by_ref("R1")
    # R1.pin1 at (80, 80), R1.pin2 at (80, 160). The wire (80,80)-(80,96) means
    # (80,80) and (80,96) share a UF root, but (80,160) is its own root. Both
    # flags target the (80,80)-(80,96) component. Net for that component is
    # 'alpha' (first-wins). R1.pin2's component has no flag → synthetic 'n1'.
    assert "alpha" in r1.pins.values()
    assert any("alpha" in str(rec.message) and "beta" in str(rec.message) for rec in w)
```

Run: `uv run pytest tests/unit/test_ltspice_asc.py -v`
Expected: all PASS.

- [ ] **Step 3.4: Run full suite**

Run: `uv run pytest`
Expected: all pass.

- [ ] **Step 3.5: Lint, format, type-check**

Run: `uv run ruff format && uv run ruff check && uv run mypy src`

- [ ] **Step 3.6: Commit**

```bash
git add src/wirewright/parse/ltspice_asc.py tests/unit/test_ltspice_asc.py
git commit -m "feat(parse): implement .asc parser with union-find net recovery"
```

---

## Task 4: Round-trip integration tests (full + connectivity-isomorphism)

**Background.** With Tasks 1–3 in place we can prove the IR ↔ `.asc` boundary is symmetric. Two test variants:

- **All-flagged** test: every net in the synthetic input is flagged. Round-trip preserves names, components, wires, flags, directives.
- **Connectivity-isomorphism** test: at least one un-flagged interior net. Round-trip cannot preserve the synthetic name (`n1` vs `n2` etc.), so we assert there exists a *bijection* between original net names and parsed net names such that for every component, applying the bijection to original pins yields parsed pins. This is the actual round-trip property the IR ↔ `.asc` boundary is supposed to guarantee.

Lossy properties (per parser docstring): `Net.is_power`, `Schematic.nets` ordering, `Component.spice_prefix` for standard prefixes. Tests assert the lossiness explicitly so future changes that accidentally lose more get caught.

**Files:**
- Create: `tests/integration/test_round_trip.py`

- [ ] **Step 4.1: Write the round-trip test module**

Create `tests/integration/test_round_trip.py`:

```python
"""End-to-end round-trip: synthetic IR → .asc → IR.

Pure synthetic data; no fixture dependencies.
"""

from __future__ import annotations

import warnings

import pytest

from wirewright.emit.asc import emit_asc
from wirewright.ir.model import Component, Flag, Net, Schematic, Wire
from wirewright.parse.ltspice_asc import parse_asc_text


def _flagged_two_resistor_schematic() -> Schematic:
    """Two resistors in series with every net flagged."""
    return Schematic(
        components=[
            Component(ref="R1", symbol="res", value="10k",
                      pins={"1": "n1", "2": "vin"}, spice_prefix="R",
                      x=64, y=64, orientation="R0"),
            Component(ref="R2", symbol="res", value="10k",
                      pins={"1": "n1", "2": "0"}, spice_prefix="R",
                      x=256, y=64, orientation="R0"),
        ],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
        wires=[
            Wire(80, 80, 80, 48),    # R1.pin1 → bend
            Wire(80, 48, 272, 48),   # bend (n1)
            Wire(272, 48, 272, 80),  # bend → R2.pin1
        ],
        flags=[
            Flag(80, 160, "vin"),    # at R1.pin2
            Flag(80, 48, "n1"),
            Flag(272, 160, "0"),     # at R2.pin2
        ],
        directives=[".tran 1m"],
    )


def _three_resistor_with_unflagged_internal_net() -> Schematic:
    """Three resistors in series with the middle node intentionally un-flagged.

    The parser must re-discover this net via union-find and assign it a
    synthetic name (n1 / n2 / etc.). The test asserts isomorphism, not name
    identity.
    """
    return Schematic(
        components=[
            Component(ref="R1", symbol="res", value="1k",
                      pins={"1": "internal_a", "2": "vin"}, spice_prefix="R",
                      x=64, y=64, orientation="R0"),
            Component(ref="R2", symbol="res", value="1k",
                      pins={"1": "internal_a", "2": "internal_b"}, spice_prefix="R",
                      x=256, y=64, orientation="R0"),
            Component(ref="R3", symbol="res", value="1k",
                      pins={"1": "internal_b", "2": "0"}, spice_prefix="R",
                      x=448, y=64, orientation="R0"),
        ],
        nets=[
            Net("vin"),
            Net("internal_a"),  # un-flagged
            Net("internal_b"),  # un-flagged
            Net("0", is_ground=True),
        ],
        wires=[
            # n1 (internal_a): R1.pin1 = (80, 80) ↔ R2.pin1 = (272, 80)
            Wire(80, 80, 80, 48), Wire(80, 48, 272, 48), Wire(272, 48, 272, 80),
            # n2 (internal_b): R2.pin2 = (272, 160) ↔ R3.pin1 = (464, 80)
            Wire(272, 160, 272, 192), Wire(272, 192, 464, 192),
            Wire(464, 48, 464, 80), Wire(464, 192, 464, 48),
        ],
        flags=[
            Flag(80, 160, "vin"),    # R1.pin2 only
            Flag(464, 160, "0"),     # R3.pin2 only
            # internal_a and internal_b deliberately un-flagged.
        ],
        directives=[],
    )


# ----------------------------- All-flagged tests -----------------------------


def test_round_trip_preserves_components() -> None:
    original = _flagged_two_resistor_schematic()
    parsed = parse_asc_text(emit_asc(original))
    refs_a = {c.ref for c in original.components}
    refs_b = {c.ref for c in parsed.components}
    assert refs_a == refs_b
    for ref in refs_a:
        a = original.component_by_ref(ref)
        b = parsed.component_by_ref(ref)
        assert (a.symbol, a.value, a.x, a.y, a.orientation) == (
            b.symbol, b.value, b.x, b.y, b.orientation,
        )


def test_round_trip_preserves_pin_connectivity() -> None:
    original = _flagged_two_resistor_schematic()
    parsed = parse_asc_text(emit_asc(original))
    for ref in {c.ref for c in original.components}:
        assert parsed.component_by_ref(ref).pins == original.component_by_ref(ref).pins


def test_round_trip_preserves_wires() -> None:
    original = _flagged_two_resistor_schematic()
    parsed = parse_asc_text(emit_asc(original))
    assert (
        {(w.x1, w.y1, w.x2, w.y2) for w in original.wires}
        == {(w.x1, w.y1, w.x2, w.y2) for w in parsed.wires}
    )


def test_round_trip_preserves_flags() -> None:
    original = _flagged_two_resistor_schematic()
    parsed = parse_asc_text(emit_asc(original))
    assert (
        {(f.x, f.y, f.net) for f in original.flags}
        == {(f.x, f.y, f.net) for f in parsed.flags}
    )


def test_round_trip_preserves_directives() -> None:
    original = _flagged_two_resistor_schematic()
    parsed = parse_asc_text(emit_asc(original))
    assert parsed.directives == original.directives


def test_round_trip_preserves_net_names() -> None:
    original = _flagged_two_resistor_schematic()
    parsed = parse_asc_text(emit_asc(original))
    assert {n.name for n in original.nets} == {n.name for n in parsed.nets}


# -------------------- Connectivity-isomorphism test ---------------------


def _connectivity_signature(s: Schematic) -> dict[str, frozenset[tuple[str, str]]]:
    """For each net name, the frozenset of (component_ref, pin_name) tuples on it."""
    sig: dict[str, set[tuple[str, str]]] = {}
    for c in s.components:
        for pin_name, net_name in c.pins.items():
            sig.setdefault(net_name, set()).add((c.ref, pin_name))
    return {k: frozenset(v) for k, v in sig.items()}


def test_round_trip_with_unflagged_nets_preserves_connectivity_isomorphism() -> None:
    """Net names may be renamed by the parser; topology must still match."""
    original = _three_resistor_with_unflagged_internal_net()
    parsed = parse_asc_text(emit_asc(original))

    sig_a = _connectivity_signature(original)
    sig_b = _connectivity_signature(parsed)

    # Same number of nets, same multiset of (ref, pin) frozensets — the rest
    # is just naming. If both sides have the same set of "net signatures"
    # (frozensets of (ref, pin) tuples), then a bijection exists by
    # construction, since each frozenset is unique modulo isomorphic graphs.
    assert sorted(sig_a.values()) == sorted(sig_b.values())


# -------------------- Lossy-property tests (documentation) ---------------------


def test_round_trip_drops_is_power_flag() -> None:
    original = _flagged_two_resistor_schematic()
    # Mark 'vin' as power; should NOT survive round-trip.
    for n in original.nets:
        if n.name == "vin":
            n.is_power = True
    parsed = parse_asc_text(emit_asc(original))
    parsed_vin = next(n for n in parsed.nets if n.name == "vin")
    assert parsed_vin.is_power is False  # documented loss; emitter has no convention


def test_round_trip_drops_standard_spice_prefix() -> None:
    """Standard prefixes (R/C/L/V/I/D/Q/M) are not written by the emitter."""
    original = _flagged_two_resistor_schematic()
    parsed = parse_asc_text(emit_asc(original))
    r1_parsed = parsed.component_by_ref("R1")
    assert r1_parsed.spice_prefix is None  # documented loss; emitter omits standard


def test_round_trip_preserves_nonstandard_spice_prefix() -> None:
    """Non-standard prefixes (e.g. 'B', 'E') ARE written and round-trip."""
    original = _flagged_two_resistor_schematic()
    # Flip R1's prefix to 'B' to force emission of SYMATTR Prefix.
    original.component_by_ref("R1").spice_prefix = "B"
    parsed = parse_asc_text(emit_asc(original))
    assert parsed.component_by_ref("R1").spice_prefix == "B"
```

- [ ] **Step 4.2: Run round-trip tests**

Run: `uv run pytest tests/integration/test_round_trip.py -v`
Expected: all PASS.

- [ ] **Step 4.3: Run full suite**

Run: `uv run pytest`
Expected: all pass.

- [ ] **Step 4.4: Lint, format, type-check**

Run: `uv run ruff format && uv run ruff check && uv run mypy src`

- [ ] **Step 4.5: Commit**

```bash
git add tests/integration/test_round_trip.py
git commit -m "test(integration): round-trip IR → .asc → IR with isomorphism + lossy-property assertions"
```

---

## Task 5: Mark specs stable; document round-trip lossy properties

**Background.** The IR and ASC emitter specs need their status flipped from "draft" to "stable in v0.1". The IR spec invariant 7 should be reworded to clarify it's guaranteed by construction. Round-trip lossy properties (is_power, nets ordering, standard spice_prefix, non-grid-aligned-bbox-not-allowed) need to be documented in the spec text. Both open questions in `ir.md` are resolved consistently (deferred to ADR-0002).

Use the `spec-writer` agent for the spec touches per CLAUDE.md project rule.

**Files:**
- Modify: `docs/specs/ir.md` (status, invariant 7 wording, open questions section, lossy-property note)
- Modify: `docs/specs/asc-emitter.md` (status, lossy-property note)

- [ ] **Step 5.1: Update IR spec via spec-writer agent**

Dispatch `spec-writer` agent with prompt:

> "In `/Users/glnds/source/hoh/wirewright/docs/specs/ir.md`:
>
> 1. Change line 3 from `**Status**: draft, will stabilize in Phase 1.` to `**Status**: stable in v0.1.`
>
> 2. Reword invariant 7 in the Invariants section from `After placement, every component pin's absolute position (computed from x, y, orientation, and the symbol's pin offset) lies on the grid.` to `Pin absolute positions are guaranteed to lie on the grid by construction: invariant 5 (component on grid) plus the registration-time assertion in wirewright.symbols.builtin that every registered pin offset is a multiple of LTSPICE_GRID. Not separately checked at runtime.`
>
> 3. Replace the entire 'Open questions' section (currently two bullets about Component.pin_directions and Net.signal_kind) with a single sentence: 'Per ADR-0002, post-1.0 IR changes will be tracked by superseding ADRs. Both pin-direction hints (for opamp +/-/OUT signal flow) and signal-kind tags (audio/CV/gate) remain unscoped for v0.1; revisit if pattern matching needs them.'
>
> 4. Add a new section before 'Open questions' (now removed in step 3) titled '## Round-trip lossy properties' with the body: 'The IR ↔ .asc boundary preserves connectivity and component placement, but the following are NOT preserved across emit_asc → parse_asc_text: (a) Net.is_power flagging — no .asc convention to mark a net as power, so all parsed nets have is_power=False; (b) Schematic.nets ordering — emitter does not write nets explicitly; parser builds them in pin-iteration order; (c) Component.spice_prefix for standard prefixes (R/C/L/V/I/D/Q/M) — emitter only writes SYMATTR Prefix for non-standard prefixes since LTspice infers standard ones from symbol; (d) free TEXT comments (`;`-prefixed) — no IR field for them in v0.1.'
>
> No other changes."

- [ ] **Step 5.2: Update ASC emitter spec via spec-writer agent**

Dispatch `spec-writer` agent with prompt:

> "In `/Users/glnds/source/hoh/wirewright/docs/specs/asc-emitter.md`:
>
> 1. Change line 3 from `**Status**: draft, will stabilize in Phase 1.` to `**Status**: stable in v0.1.`
>
> 2. Add a new section before 'Open questions' titled '## Round-trip lossy properties' with: 'See docs/specs/ir.md § Round-trip lossy properties for the canonical list. Specifically the emitter does not write SYMATTR Prefix for standard prefixes (R/C/L/V/I/D/Q/M) since LTspice infers them, and does not write any explicit net declarations (nets are reconstructed from connectivity by the .asc parser).'
>
> 3. In the 'Output ordering' section, append: 'Wire endpoint order is NOT normalized — Wire(80, 80, 80, 48) and Wire(80, 48, 80, 80) are both emitted as written. Round-trip relies on the emitter's deterministic serialization order, not on canonical wire orientation. Wire normalization (smaller endpoint first) is a v0.2 spec change, not v0.1.'
>
> No other changes."

- [ ] **Step 5.3: Run full test suite as a smoke**

Run: `uv run pytest && uv run ruff check && uv run mypy src`
Expected: all green (no code touched in Task 5, just specs).

- [ ] **Step 5.4: Commit**

```bash
git add docs/specs/ir.md docs/specs/asc-emitter.md
git commit -m "docs(specs): mark IR and ASC emitter stable in v0.1; document round-trip lossy properties"
```

---

## Task 6: Update PLAN.md DoD and CLAUDE.md phase tracker

**Background.** `docs/PLAN.md` Phase 1 DoD line 34 says "ASC emitter passes round-trip on all three fixtures (parse hand-drawn `.asc` → IR → emit `.asc` → opens in LTspice with same connectivity)." This plan delivers round-trip on synthetic data only; the hand-drawn-fixture round-trip is a user-author task gated on LTspice GUI work. Phase 1 is "implementation complete" but the hand-drawn-fixture DoD bullet is honestly deferred.

**Files:**
- Modify: `docs/PLAN.md` (Phase 1 DoD)
- Modify: `CLAUDE.md` (phase tracker line)

- [ ] **Step 6.1: Update PLAN.md Phase 1 DoD**

In `/Users/glnds/source/hoh/wirewright/docs/PLAN.md`, find the Phase 1 DoD section (around line 28-36). Replace the line `- ASC emitter passes round-trip on all three fixtures (parse hand-drawn `.asc` → IR → emit `.asc` → opens in LTspice with same connectivity).` with two lines:

```markdown
- ASC emitter round-trip verified on synthetic Schematics (Task 4 of Phase 1 plan): all components, wires, flags, directives, and connectivity isomorphism preserved.
- Hand-drawn `.asc` round-trip on the canonical fixtures (`divider.asc`, `tb303-envelope.asc`, `tb303-vco-integrated.asc`) is deferred — these `.asc` files are author-only deliverables requiring LTspice GUI authoring. The hard-tier fixture additionally requires Phase 2 SPICE parser to land first. Marked DEFERRED: target is end-of-Phase-2 once user has authored the `.asc` reference files.
```

- [ ] **Step 6.2: Bump CLAUDE.md phase tracker**

In `/Users/glnds/source/hoh/wirewright/CLAUDE.md`, find the line `**Current phase**: 0 (bootstrap)` and replace with:

```markdown
**Current phase**: 1 implementation complete; hand-drawn fixture round-trip deferred. Phase 2 starting.
```

Run: `grep -n "Current phase" CLAUDE.md`
Expected: matches the new line.

- [ ] **Step 6.3: Run full test suite as final smoke**

Run: `uv run pytest && uv run ruff check && uv run mypy src`

- [ ] **Step 6.4: Commit**

```bash
git add docs/PLAN.md CLAUDE.md
git commit -m "docs: bump phase tracker; honestly defer hand-drawn fixture DoD bullet"
```

---

## Self-Review

**Spec coverage:**
- IR spec invariants 5 (wire endpoints on grid): unchanged, already in `_check_grid_alignment`. ✓
- IR spec invariant 6 (no bbox overlap): Task 2. ✓
- IR spec invariant 7 (pin positions on grid): now reworded as "by construction"; the registration-time assertion in builtin.py (Task 1.5) catches violations at module load. ✓
- ASC emitter spec line types: Task 3 covers WIRE/FLAG/SYMBOL/SYMATTR/TEXT. IOPIN documented as not used. ✓
- ASC emitter spec libname-with-folder-prefix: Task 3 strips for lookup, preserves on Component.symbol for round-trip. ✓
- ASC emitter spec pin-attachment "exactly on" rule: parser uses lattice-coverage (intentional leniency for hand-drawn input); emitter still enforces strict snapping at output time. Documented. ✓
- Phase 1 deliverable list (per `docs/PLAN.md`): expanded symbol registry — Task 1 ✓; full validate_placed invariants — Task 2 ✓; parse/ltspice_asc.py — Task 3 ✓; round-trip test — Task 4 ✓; emit/asy.py — explicitly out of scope per project plan; hand-drawn fixture DoD bullet — explicitly deferred per Task 6. ✓

**Placeholder scan:**
- No "TBD", "TODO", "implement later", or "appropriate error handling" placeholders.
- Every code step shows the exact code to add or replace.
- Every command shows expected output behavior.

**Type consistency:**
- `Component.pins: dict[str, str]`: consistent across Tasks 1, 3, 4.
- `SymbolGeometry.pins: dict[str, tuple[int, int]]`: consistent.
- `_UnionFind` keys: `tuple[int, int]`: consistent.
- `Orientation`: validated via `get_args(Orientation)` and `frozenset` membership; cast applied after narrowing.
- `AscParseError`: defined once in Task 3.2; imported and matched in tests.
- Function names: `parse_asc_text`/`parse_asc_file` (public), `_recover_nets`/`_wire_lattice_points`/`_strip_lib_folder` (private), `_UnionFind` (private), `resolve_asy_path`/`parse_asy_pins_by_spice_order`/`parse_asy_file` (public lib_index).

**Review-finding traceability:**

| Finding | Severity | Addressed by |
|---------|----------|--------------|
| B1 (no bbox audit) | Blocker | Task 1.3 adds `test_pin_bboxes_match_asy_file` |
| B2 (pin-grid invariant is dead code) | Blocker | Task 1.5 moves to module-load assertion; Task 2 drops runtime check |
| B3 (Wire constructor errors lose line context) | Blocker | Task 3.2's WIRE branch wraps in try/except and re-raises |
| B5 (is_power not preserved) | Blocker | Task 4.1's `test_round_trip_drops_is_power_flag`; Task 5.1 documents in IR spec |
| B6 (two-flags hard-fail rejects valid LTspice) | Blocker | Task 3.2's `_recover_nets` warns + first-flag-wins; Task 3.3's `test_conflicting_flag_names_warn_first_wins` |
| M2 (Opamps/opamp2 prefix not handled) | Major | Task 3.2's `_strip_lib_folder` + Task 3.3's `test_lib_folder_prefix_stripped_for_registry_lookup` |
| M3 (round-trip skips un-flagged nets) | Major | Task 4.1's `test_round_trip_with_unflagged_nets_preserves_connectivity_isomorphism` |
| M4 (Phase 1 DoD vs phase tracker) | Major | Task 6.1 updates PLAN.md DoD; Task 6.2 phrases tracker honestly |
| M5 (resolve_asy_path belongs in lib_index) | Major | Task 1.1 promotes it |
| M7 (nets ordering not preserved) | Major | Task 5.1 documents in IR spec |
| M8 (cast-after-validation type narrowing) | Major | Task 3.2 uses `get_args(Orientation)` + `frozenset` |
| N1 (spice_prefix not preserved) | Minor | Task 4.1's `test_round_trip_drops_standard_spice_prefix` + `test_round_trip_preserves_nonstandard_spice_prefix` |
| N2 (silent SYMATTR drop) | Minor | Task 3.2 warns; Task 3.3's `test_unknown_symattr_emits_warning` |
| N3 (silent unknown-line-type drop) | Minor | Task 3.2 warns; Task 3.3's `test_unknown_line_type_emits_warning` |
| N4 (very long wires) | Minor | Task 3.2's `_LATTICE_LIMIT` raises `AscParseError` |
| N5 (open-question consistency) | Minor | Task 5.1 resolves both consistently |
| N7 (ruff format vs --check) | Minor | All steps use `ruff format` (auto-apply) |
| N8 (misleading test name) | Minor | The misleading test from rev 1 is removed entirely; clean-asc test takes its place |
| N9 (wire endpoint normalization) | Minor | Task 5.2 documents in asc-emitter spec |

---

## Execution

This plan is rev 2 and incorporates all `phase-1.review.md` findings. Per CLAUDE.md plan-review routing, **a second adversarial review is NOT performed in the same session**: if rev 2 still fails review on subsequent independent inspection, that is a NEEDS_HUMAN promotion, not a third rewrite.

Execute via `superpowers:subagent-driven-development` with one fresh subagent per task. Six tasks are sequential — Task 2 depends on Task 1's bbox correctness; Task 3 depends on Task 1's symbol registry; Task 4 depends on Tasks 1–3; Task 5 depends on Tasks 1–4 having landed; Task 6 depends on Task 5. Practical ordering: Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6.
