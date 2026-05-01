# wirewright development guide for Claude Code

## What this is

A SPICE netlist to LTspice `.asc` placer. Reads a netlist, decides where every component and wire goes, writes a syntactically valid `.asc` file that LTspice can open. Quality target: human-readable enough for breadboarding and debugging, not commercial-tool quality.

## Architecture in one breath

`netlist file → parse/spice.py → IR (ir/model.py) → placers/{naive,elk,hola}.py → IR with coords → emit/asc.py → .asc file`. The IR is the stable contract between every layer.

## Hard rules

- Specs in `docs/specs/` are authoritative. If code disagrees with the spec, the spec is right unless you update it explicitly with a commit message explaining why.
- Every placer implements `placers.base.Placer`. No exceptions.
- Symbol pin offsets only live in `src/wirewright/symbols/`. Do not hardcode pin positions anywhere else.
- Coordinates in IR are integers in LTspice grid units (16 mils per unit). Floating-point coordinates are a bug.
- Never commit anything that fails `uv run pytest` or `uv run ruff check`.
- ADRs in `docs/adr/` record decisions that are non-trivial to reverse. If you change one, supersede it with a new ADR rather than editing in place.

## Running things

```bash
uv sync                                     # install
uv run wirewright --help                    # CLI help
uv run wirewright demo                      # trivial 2-resistor demo, end-to-end
uv run wirewright render <netlist> -o <out.asc> [--placer naive|elk|hola]
uv run pytest                               # run tests
uv run pytest tests/integration -k easy     # one fixture
uv run ruff check                           # lint
uv run mypy src                             # types
uv run python tools/render_compare.py fixtures/medium    # A/B both placers (Phase 4+)
```

## Phase tracker

See `docs/PLAN.md` for the full plan. Update the line below when a phase is complete.

**Current phase**: 4 complete (with HOLA limitations); Phase 5 (pattern recognition) starting.

## Workflow expectations

1. Read the relevant spec under `docs/specs/` before changing code.
2. Write or update tests before changing implementation code.
3. Use the `adversarial-reviewer` agent on any non-trivial PR.
4. If you discover the spec is wrong, fix the spec first as its own commit. Do not silently make the code disagree with the spec.
5. When adding a new placer, copy `placers/grid_naive.py` as the structural template.
6. When adding a new analog idiom to the pattern library, add a fixture that triggers it and a test that asserts it gets matched.

## Things to avoid

- Inventing new coordinate systems. Use IR grid units everywhere internally; only convert when emitting.
- Catching exceptions silently. If something fails, fail loudly so the cause is obvious.
- Mixing concerns. The placer must not know about `.asc` file format. The emitter must not know about LTspice symbol libraries beyond pin offsets. The parser must not know about placement.
- Fancy features before the basics work. Phase 5 (patterns) is gated on Phase 4 (HOLA baseline).

## Where to find context

- Architecture overview: `docs/design.md`
- Phased plan: `docs/PLAN.md`
- IR contract: `docs/specs/ir.md`
- Placer interface contract: `docs/specs/placer-interface.md`
- ASC emitter contract: `docs/specs/asc-emitter.md`
- ADRs explaining the why: `docs/adr/`
