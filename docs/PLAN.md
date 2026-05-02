# wirewright development plan

This is the canonical phased plan. Each phase has a clear scope, definition-of-done, and dependency on prior phases.

The North Star: a deterministic, configurable placer that converts SPICE netlists into readable LTspice `.asc` schematics, with pluggable placement back ends (ELK and HOLA) and a pattern-recognition layer for analog idioms.

---

## Phase 0: bootstrap

**Scope**: project skeleton, CI, fixtures, working trivial demo end-to-end.

**Done when**:
- `uv run wirewright --help` works.
- `uv run wirewright demo` runs a 2-resistor circuit through the full pipeline (IR → naive placer → ASC emitter) and prints a syntactically valid `.asc` to stdout.
- `uv run pytest` passes.
- Three fixture circuits checked into `tests/fixtures/` with hand-drawn `.asc`, SPICE netlist, and `description.md`.
- ADRs 0001-0004 written.
- All Phase 1 specs drafted (even if not finalized).

**Status**: in progress.

---

## Phase 1: IR and ASC emitter

**Scope**: lock down the internal representation. Build a real ASC emitter that handles the symbol set we care about for v0.1.

**Done when**:
- `docs/specs/ir.md` is complete and stable.
- `docs/specs/asc-emitter.md` is complete and stable.
- The full IR (`Component`, `Net`, `Wire`, `Schematic`, `Pin`) is implemented with validation.
- `src/wirewright/symbols/builtin.py` has accurate pin offsets verified against actual `.asy` files for: `res`, `cap`, `ind`, `npn`, `pnp`, `nmos`, `pmos`, `diode`, `opamp2`, `voltage`, `current`, `polcap`.
- ASC emitter round-trip verified on synthetic Schematics (Phase 1 plan Task 4): components, wires, flags, directives, and connectivity isomorphism preserved. Tests in `tests/integration/test_round_trip.py`.
- DEFERRED: hand-drawn `.asc` round-trip on the canonical fixtures (`divider.asc`, `tb303-envelope.asc`, `tb303-vco-integrated.asc`) is gated on user-author work in LTspice GUI. The hard-tier fixture additionally requires Phase 2 SPICE parser to land. Target: end-of-Phase-2 once `.asc` reference files have been authored.
- A unit test hand-constructs a 2-resistor `Schematic`, emits an `.asc`, and the file opens in LTspice with the wires actually connected.

**Depends on**: Phase 0.

---

## Phase 2: SPICE netlist parser

**Scope**: parse SPICE / LTspice netlist files into IR. Subcircuits are flattened.

**Done when**:
- `docs/specs/netlist-parser.md` is complete.
- All three fixture netlists parse cleanly into IR.
- Round-trip test passes: parse fixture `.net` → IR → emit `.asc` (with hand-supplied coords from the existing fixture `.asc`) → opens in LTspice with same connectivity as the original.

**Depends on**: Phase 1.

**Status**: complete in v0.1. LED/Zener/Schottky discrimination from `.MODEL D` parameters deferred (every `D` maps to symbol `diode`); 4-node Q (substrate) deferred (rejected with `ParseError`); local `.MODEL` inside `.SUBCKT` deferred (rejected with `ParseError`).

---

## Phase 3: HOLA + libavoid + expanded fixtures

**Scope**: the pipeline becomes real. HOLA is wired up as the only placer (per ADR-0005), `routing/orthogonal.py` becomes a libavoid wrapper for proper object-avoiding orthogonal connector routing, and the fixture set expands to 8–12 circuits each with a recorded "verdict + failure category" by the user.

**Done when**:
- `pyhola` build documented in `docs/build-hola.md` (the `hola-graph` PyPI wheel covers macOS arm64 / Linux x86_64; the doc records the source-build path for unsupported platforms).
- `src/wirewright/placers/hola.py` implements the `Placer` interface (already done as part of the spike that produced ADR-0005).
- `routing/orthogonal.py` wraps libavoid (Adaptagrams' object-avoiding orthogonal connector router). Replaces the v0.1 inline pairwise-L-shape routing for HOLA output.
- `wirewright render <netlist> --placer hola` works on every shipping fixture except the 3 known-abort fixtures (`tb303-vco-saw-cliptop`, `-bottom`, `tb303-vco-integrated`). Those use `--placer naive` as fallback.
- 8–12 expanded fixtures land in `tests/fixtures/` with `description.md` per fixture (user authors netlists; scaffolding written by the agent). Each rendered output reviewed by the user, with verdict (acceptable / needs-pattern / needs-routing / abort) and failure-category tag recorded.
- The user-recorded failure log becomes the input to Phase 4.

**Depends on**: Phase 2.

**Status**: complete in v0.1. HOLA placer + subprocess isolation already shipped from the spike (per ADR-0005). Routing improved with obstacle-aware L-shape selection in `routing/orthogonal.py` (libavoid wrapper deferred — recon showed no usable Python binding to libavoid's `Router`/`ConnRef`; the `hola_graph` package exposes only avoid's geometry primitives. Pure-Python obstacle avoidance suffices for v0.1; libavoid wrapping moves to a future phase). `docs/build-hola.md` documents the wheel + source-build paths. Fixture scaffolding ships in `tools/add_fixture.py` + `tests/fixtures/_TEMPLATE.description.md`. Review tool ships in `tools/review.py` — produces a markdown verdict table the user fills in. The user-recorded failure log becomes Phase 4's input.

---

## Phase 4 (was 5): patterns driven by Phase 3's failure log

**Scope**: pattern recognition specifically targeting the failure categories surfaced in Phase 3. Patterns aren't written speculatively; each one fixes a categorized failure from the Phase 3 review.

**Done when**:
- For each "needs-pattern" verdict from Phase 3, a pattern template lands in `src/wirewright/patterns/library/` with a triggering fixture and a matcher test.
- Re-rendering each affected fixture with `--use-patterns` produces output the user marks acceptable.
- `docs/notes/pattern-coverage.md` updated to map each shipping pattern to the Phase 3 failure it fixes.
- HOLA honors `pinned` hints (so `--use-patterns --placer hola` actually changes layout). v0.1 only NaivePlacer honors them; v0.2 lifts that to HOLA via `hola_graph.HolaGraph.add_node(x=, y=)` initial positions or post-layout translation.

**Depends on**: Phase 3. This is the last phase before v0.1 ships.

**Status**: deferred to v0.2. The user's Phase 3 visual review found HOLA output acceptable across the corpus with only minor wire-overlap issues — i.e. the failure log doesn't justify speculative pattern work for v0.1, per ADR-0005's discipline (write patterns that fix categorized failures, not pre-author a library and hope). The 7 starter templates from the spike (`rc_lowpass`, `rc_highpass`, `diff_pair_{npn,pnp}`, `current_mirror_{npn,pnp}`, `common_emitter_npn`) and the matcher infrastructure stay in the repo as v0.2 seed; they correctly match real idioms in the existing fixtures (the 5 expo-converter fixtures all match `current_mirror_pnp` + `diff_pair_npn`; the VCF chain fixtures match `rc_lowpass` 4× each). What's missing for v0.2: HOLA pinned-hint integration via `hola_graph.HolaGraph.add_node(x=, y=)` so `--use-patterns --placer hola` actually changes layout (currently only NaivePlacer honors `pinned`).

---

(no Phase 5 — Phase 4 is the last phase before v0.1 ships.)

---

## Out of scope for v0.x

- GUI of any kind.
- Hierarchical schematics (everything is flattened in the parser).
- Custom symbol generation. We use only the LTspice standard library.
- LLM-based placement (worth experimenting with EEschematic on a side branch, but not in core).
- PCB layout. This tool stops at `.asc`.
- Reverse direction (`.asc` → improved `.asc`).

## Re-evaluation milestones

- End of Phase 3: review the failure-category log for the expanded fixtures. Decide which categories are pattern-shaped (Phase 4) vs routing-shaped (libavoid follow-up) vs HOLA-internal (v0.2 backlog).
- End of Phase 4: ship v0.1 if the medium/hard fixtures are acceptable. Otherwise iterate on patterns.
- Post-v0.1: revisit ADR-0004's "two placers" question only if a real second use case appears (ADR-0005 for the current decision).
