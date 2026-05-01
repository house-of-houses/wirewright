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

## Phase 3: ELK baseline

**Scope**: integrate Eclipse Layout Kernel via Node.js bridge as the first real placer.

**Done when**:
- `tools/elk-bridge/` has a working Node.js script that does ELK layout via stdin/stdout JSON.
- `src/wirewright/placers/elk.py` implements the `Placer` interface.
- `wirewright render <netlist> -o <out.asc> --placer elk` works on all three fixtures.
- The easy fixture renders to a layout that opens cleanly in LTspice and is at least as readable as the existing community state of the art for digital layered layout.
- The medium and hard fixtures render to valid `.asc` even if the layout is not yet good for analog.
- Power and ground nets are handled as global rails (top and bottom of canvas), not as ELK edges.
- `docs/specs/placer-interface.md` is finalized based on real implementation experience.

**Depends on**: Phase 2.

**Status**: complete in v0.1. ELK Layered baseline ships; canonical fixtures render via `--placer elk`. Strict connectivity isomorphism is preserved on the easy fixture; medium/hard fixtures render to valid `.asc` but layout-induced wire overlaps may merge nets at the parser level (acknowledged v0.1 quality limitation).

---

## Phase 4: HOLA baseline

**Scope**: integrate HOLA (Human-like Orthogonal Layout) via pyhola as the second real placer.

**Done when**:
- pyhola builds against adaptagrams in a documented procedure (`docs/build-hola.md`).
- `src/wirewright/placers/hola.py` implements the `Placer` interface.
- `wirewright render <netlist> --placer hola` works on all three fixtures.
- `tools/render_compare.py` produces a side-by-side report of ELK vs HOLA for any fixture.
- You have a documented honest opinion in `docs/notes/elk-vs-hola.md` about which placer is closer to your hand-drawn target on which kinds of circuits.

**Depends on**: Phase 3. May be skipped or delayed if pyhola build is intractable; not a blocker for shipping a v0.1 with ELK only.

**Status**: complete in v0.1 with caveats. `hola-graph` PyPI wheel covers macOS arm64 / Linux x86_64 (no manual `adaptagrams` build needed; obsoletes the `docs/build-hola.md` DoD bullet). HOLA renders divider and tb303-envelope; aborts with C++ `faces.cpp` assertion on tb303-vco-integrated (planarity check passes but biconnectivity-related internal assertion still fires). Subprocess isolation deferred to v0.2. Side-by-side comparison tool ships at `tools/render_compare.py`; opinion documented at `docs/notes/elk-vs-hola.md`.

---

## Phase 5: pattern recognition

**Scope**: a matcher that finds analog idioms in the netlist and applies template placements before the underlying placer runs.

**Done when**:
- `docs/specs/pattern-library.md` defines the YAML template format.
- `src/wirewright/patterns/matcher.py` uses NetworkX VF2 (or VF3 if we wrap it) to find matches.
- The library has at least these templates: differential pair (NPN, PNP, NMOS, PMOS), current mirror (NPN, PNP, NMOS, PMOS), common-emitter stage, RC low-pass, RC high-pass, opamp inverting, opamp non-inverting, opamp Sallen-Key low-pass, BJT diff amp with current mirror load, TB-303 ladder rung.
- Each template has a fixture that triggers it and a test that asserts the match.
- The medium and hard fixtures are now visibly better than they were at the end of Phase 4.

**Depends on**: Phase 4. Optional for v0.1 if Phase 4 output is already acceptable.

---

## Out of scope for v0.x

- GUI of any kind.
- Hierarchical schematics (everything is flattened in the parser).
- Custom symbol generation. We use only the LTspice standard library.
- LLM-based placement (worth experimenting with EEschematic on a side branch, but not in core).
- PCB layout. This tool stops at `.asc`.
- Reverse direction (`.asc` → improved `.asc`).

## Re-evaluation milestones

- After Phase 3: decide if v0.1 ships with ELK only or if HOLA is required.
- After Phase 4: decide if v0.2 needs Phase 5 (patterns) or if the bare HOLA output is good enough on real Eurorack circuits.
- After Phase 5: decide if there is appetite for an LLM-based v0.3 path.
