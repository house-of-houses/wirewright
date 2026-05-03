# Changelog

All notable changes to wirewright. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
