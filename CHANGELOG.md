# Changelog

All notable changes to wirewright. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Wire-connectivity oracle** —
  `ir.validate.check_wires_induce_exact_nets(sch, strict=False)` catches
  wire-induced net shorts via union-find over pin positions + wire
  endpoints + wire-interior crossings. `validate_placed` calls it with
  `strict=False` (logs `WARNING`). Strict callers raise
  `ValidationError`. See invariant 9 in `docs/specs/ir.md`.
- **Pin-aware routing** —
  `routing.orthogonal.route_avoiding(..., pin_obstacles=...)` penalizes
  paths whose corners or segment interiors land on other-net pins.
  Score tuple is `(pin_hits, bbox_crossings, total_length)`. Z-detour
  candidates now trigger on pin obstacles alone. Both `HolaPlacer` and
  `NaivePlacer` wire this up.

### Fixed

- **Rails no longer short through stacked flag positions.** When VDD /
  VSS / GND rail flags landed on the same x column, the vertical stub
  from one rail's pin to its flag passed through another rail's flag
  position, electrically shorting the two nets. `emit_power_ground_rails`
  now routes stubs through `route_avoiding(..., pin_obstacles=...)`
  with other-rail flag positions and other-net pin positions as point
  obstacles — a colliding straight stub becomes an L-bump-out that
  clears every obstacle. Recovers 2 of the 4 known-short HOLA fixtures:
  `tb303-envelope`, `tb303-vco-saw-cliptop`.
- **`route_avoiding` honors pin obstacles on colinear endpoints.**
  Previously short-circuited to a straight `Wire(a, b)` for colinear
  endpoints without checking pin obstacles. Now generates bump-out
  candidates (±1 grid step aside) when the straight path would cross a
  pin, picks lowest-score.

### Known issues

- Of HOLA's 4 previously-shorted fixtures, **2 remain**:
  `tb303-vco-saw-cliptop-bottom` and `tb303-vco-integrated`. These show
  a different short pattern — signal-net routing through other
  signal-net pins, not rail collisions. The HOLA signal-net router
  passes `pin_obstacles` to `route_avoiding`, but `route_avoiding`'s
  current candidate set (2 L + 4 Z around obstacle extremes) can't
  always find a short-free path on dense placements. Needs HOLA
  placement-density work and/or a stronger router.

### EEschematic experiment — paused

- Side experiment on `experiment/eeschematic` branch — MLLM-based
  placer using GPT-5 vision. Divider plumbing passes end-to-end. After
  the rails fix above, `tb303-vco-saw-cliptop` was retried: the LLM
  placement itself is clean, but the experiment's strict wiring still
  fails on signal-net shorts (RAMP ↔ TRIG) — same router-candidate
  limitation that blocks HOLA's remaining 2 fixtures. Both are gated on
  the same follow-up routing work. See
  `docs/notes/eeschematic-verdict.md`. Branch retained as reference;
  not merged.

## [0.2.0] — 2026-05-03

Quality release. Every TB-303 fixture renders under `--placer hola`
without aborts, power/ground gets a sensible default rendering, and the
manual-edit feedback loop ships.

### Added

- **`--placer auto`** — tries HOLA, falls back to `naive` on
  `PlacerEngineError`. Now the default for both `wirewright render` and
  `wirewright demo`.
- **`wirewright diff <a.asc> <b.asc>`** — structured before/after diff
  on parsed `.asc` files (component moves/rotations, wire add/remove,
  flag deltas). Closes the manual-edit feedback loop.
- **`--rails {scattered,clustered,global}`** — power/ground rendering
  mode. Default `clustered` 1-D-clusters pins by x-proximity (gap
  threshold 6 grid units); each multi-pin cluster gets a short local
  rail with one FLAG, singletons drop a stub-and-FLAG in the rail band.
  `scattered` keeps a FLAG per pin; `global` is the v0.2-cycle one-rail-
  per-net behavior.
- **Z-shape detour routing** — `routing.orthogonal.route_avoiding`
  picks from 2 L plus 4 Z candidates (around obstacle bbox extremes) by
  `(crossings, total_length)`. Used by `HolaPlacer` for inter-pin wires.
- **Issue tracker** — `docs/issues/` for things we deliberately don't
  fix in core wirewright but want to remember (`0001`: HOLA aborts,
  closed; `0002`: libavoid binding wait list).

### Changed

- **HOLA aborts resolved.** `_biconnect_leaf_extras` chains every
  articulation point's leaves with virtual edges on retry after a first
  attempt aborts in `faces.cpp::identifyExternalFace`. All 3 previously-
  aborting fixtures (`tb303-vco-saw-cliptop`,
  `tb303-vco-saw-cliptop-bottom`, `tb303-vco-integrated`) now render
  via `--placer hola` directly.
- `Placer` base class accepts `rails: RailMode` in `__init__`; all three
  back ends honor it.

### Known limitations carried into v0.3

- HOLA pinned-hint integration still pending (so `--use-patterns
  --placer hola` does not yet snap to canonical pattern positions —
  matches still feed `NaivePlacer` only).
- libavoid Python binding still does not exist (issue 0002 watch list).
  Pure-Python L+Z router is what we ship.
- Hand-drawn `.asc` round-trip references still user-deliverable.

### Stats at release

- 190 unit + integration tests passing; ruff and mypy clean.
- 21/21 canonical TB-303 fixtures render under `--placer hola` directly.

[0.2.0]: https://github.com/gertd/wirewright/releases/tag/v0.2.0

## [0.1.0] — 2026-05-02

First public release. Renders SPICE netlists into LTspice `.asc` schematics
that open cleanly and are readable enough to breadboard against.

### Pipeline

- **Parse:** SPICE netlists with R, C, L, V, I, D, B, E, S, Q, M, X
  (subcircuits flattened with X-stripped namespace prefix per
  `docs/specs/netlist-parser.md`). NPN/PNP/NMOS/PMOS resolved from
  `.MODEL`. `.SUBCKT`/`.ENDS`, `.MODEL`, `.PARAM`, `.OPTIONS`, `+`
  line continuations.
- **IR + emitter:** stable IR contract in `wirewright.ir`; ASC emitter
  produces deterministic output with grid-snapped coordinates and
  natural-sort component refs.
- **Symbol library:** 18 LTspice symbols verified against the real
  `.asy` files (`res`, `cap`, `polcap`, `ind`, `diode`, `npn`, `pnp`,
  `nmos`, `nmos4`, `pmos`, `pmos4`, `voltage`, `current`, `bv`, `bi`,
  `e`, `opamp`, `opamp2`, `sw`).
- **`.asc` parser:** round-trip-able via `parse_asc_text`; recovers nets
  through union-find on coordinate equality, accepts library-folder
  prefixes (`OpAmps/opamp2`), warns on unknown SYMATTR keys / line types,
  first-flag-wins on contradictory FLAG names.

### Placers

- **`naive`** — grid placement; honors `pinned` hints; fallback for
  graphs HOLA cannot lay out.
- **`hola`** (default for real circuits) — Human-like Orthogonal Layout
  via `hola-graph >=0.1.5`. Runs in a subprocess so HOLA's C++ asserts
  surface as `PlacerEngineError` rather than killing Python.
  Disconnected non-power/ground graphs auto-stitched with virtual edges.
- **Routing:** `routing.orthogonal.l_shape_avoiding` picks the L-bend
  orientation (HV vs VH) that crosses the fewest component bbodies.

### Patterns

- NetworkX VF2 matcher with topology-constraint verification; YAML
  template format documented in `docs/specs/pattern-library.md`.
- 7 starter templates: `rc_lowpass`, `rc_highpass`, `diff_pair_{npn,pnp}`,
  `current_mirror_{npn,pnp}`, `common_emitter_npn`. All seven match real
  idioms in the canonical fixture corpus.
- `--use-patterns` flag detects idioms and feeds `pinned` hints to
  `NaivePlacer`. **HOLA does not yet honor `pinned`** — v0.2 work.

### Architecture decisions

- ADR-0005: HOLA is the only real placer; ELK was evaluated and removed
  per visual comparison on 21 TB-303 fixtures. The `Placer` ABC,
  `--placer` flag, and registry stay so a future second back end lands
  cleanly.

### Known limitations

- 3 fixtures genuinely abort inside HOLA's C++
  (`tb303-vco-saw-cliptop`, `tb303-vco-saw-cliptop-bottom`,
  `tb303-vco-integrated`). These fail gracefully now;
  use `--placer naive` as fallback.
- `--use-patterns` only changes layout when used with `--placer naive`;
  HOLA pinned-hint integration is v0.2.
- libavoid wrapping deferred — recon showed `hola_graph` exposes only
  geometry primitives, not `Router`/`ConnRef`. Pure-Python obstacle
  avoidance is the v0.1 router.
- Hand-drawn `.asc` round-trip on canonical fixtures: deferred until the
  user authors reference `.asc` files in LTspice.

### v0.2 wishlist

In rough priority order:

- HOLA pinned-hint integration so `--use-patterns --placer hola` works.
- Workaround for the 3 HOLA-abort fixtures (graph pre-conditioning or
  upstream patch to `libdialect`).
- libavoid wrapping (when a Python binding exists or someone writes one).
- Additional pattern templates *as fixtures surface specific failures*
  (per ADR-0005's discipline: don't write speculatively).

### Stats at release

- 164 unit tests passing; ruff and mypy clean.
- 21 canonical TB-303 fixtures in `tests/fixtures/`.
- 18/21 fixtures render successfully with HOLA; remaining 3 have
  graceful failure paths.

[0.1.0]: https://github.com/gertd/wirewright/releases/tag/v0.1.0
