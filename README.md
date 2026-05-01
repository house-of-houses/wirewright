# wirewright

> Auto-generate readable LTspice `.asc` schematics from SPICE netlists.

A placer that takes a SPICE netlist and writes an LTspice `.asc` file you can actually read. Built on top of established graph-layout algorithms (ELK, HOLA) with an analog-idiom pattern layer for circuits like differential pairs, current mirrors, opamp feedback networks, and TB-303-style ladder rungs.

**Status**: pre-alpha. The pipeline runs end-to-end with a trivial demo. Real circuits are coming in Phases 1-4 (see [`docs/PLAN.md`](docs/PLAN.md)).

## What this is for

You simulate analog circuits in LTspice and you have netlists, but the schematic side of the workflow is the part where you spend hours dragging things around. wirewright is a deterministic, configurable tool that does the placement for you so you can keep iterating in netlist form and regenerate the `.asc` whenever you want to look at it visually or hand it to someone else for breadboarding.

The aesthetic target is "readable enough for breadboarding and debugging," not commercial-tool quality. If you want SpiceVision PRO, buy SpiceVision PRO.

## Quick start

```bash
# install with uv (recommended)
uv sync

# or with pip in a venv
pip install -e .

# run the trivial demo (two resistors in series)
wirewright demo

# render a real netlist (Phase 3+, requires ELK or HOLA)
wirewright render path/to/circuit.net -o out.asc
```

## How it works

```
┌──────────────┐   ┌─────────┐   ┌──────────┐   ┌──────────┐
│ SPICE netlist│──▶│  parse  │──▶│    IR    │──▶│  placer  │
└──────────────┘   └─────────┘   └──────────┘   └────┬─────┘
                                                     │
                                                     ▼
┌──────────────┐   ┌─────────┐   ┌──────────────────────────┐
│   .asc file  │◀──│   emit  │◀──│ IR with x/y/orientation  │
└──────────────┘   └─────────┘   └──────────────────────────┘
```

The Internal Representation (IR) is the stable contract that decouples parsing, placement, and emission. Multiple placers plug into the same interface:

- `naive`: trivial grid placement, ships with v0.0.1 for sanity checks.
- `elk`: Eclipse Layout Kernel via a tiny Node.js bridge. Layered Sugiyama with port constraints and orthogonal routing. Best for circuits with strong directional flow.
- `hola`: Human-like Orthogonal Layout (Kieffer et al, IEEE TVCG 2016) via pyhola. Stress-majorization with port constraints, produces more compact and symmetric layouts. Best for analog with feedback and balanced sections.

A pattern-recognition layer (Phase 5) finds analog idioms like differential pairs, current mirrors, and ladder rungs in the netlist and applies template placements before the underlying placer runs.

## Project layout

```
src/wirewright/
├── ir/         internal representation (the stable contract)
├── parse/      SPICE netlist + .asc file parsing
├── emit/       IR + placement → .asc file
├── placers/    pluggable placement backends (naive, elk, hola)
├── patterns/   analog idiom matcher and template library
├── routing/    orthogonal wire routing
├── symbols/    LTspice .asy pin geometry
└── cli.py      command-line entry point

docs/
├── PLAN.md     phased development plan
├── design.md   architecture overview
├── adr/        architecture decision records
└── specs/      authoritative specifications for each component
```

The phased plan in [`docs/PLAN.md`](docs/PLAN.md) is the roadmap. Specs in [`docs/specs/`](docs/specs/) are authoritative: if code disagrees with a spec, the spec wins.

## Working with Claude Code in this repo

See [`CLAUDE.md`](CLAUDE.md) for the rules and workflow. Short version: read the spec, write a test, then change the code. Custom agents and skills live under [`.claude/`](.claude/).

## Why does this exist

The state of FOSS for "netlist to readable schematic" in early 2026 is honestly thin (see [`docs/research/`](docs/research/) for the deep-dive that motivated the project). The closest commercial tool is Concept Engineering's SpiceVision PRO, which is closed and expensive. The closest academic line is the HOLA family from Monash plus the very recent EEschematic and Schemato LLM-based work. None of those, on its own, gives you a working open-source tool you can clone and run today against a Eurorack-scale circuit. wirewright is the attempt to fill that hole.

## License

MIT. See [`LICENSE`](LICENSE).

## Acknowledgements

This project would not be possible without:

- Eclipse Layout Kernel (Sören Domrös, Reinhard von Hanxleden, et al, Kiel University)
- HOLA / Adaptagrams (Steve Kieffer, Tim Dwyer, Kim Marriott, Michael Wybrow, Monash University)
- The LTspice file format documentation in the KiCad project
- The work on EEschematic (Liu and Chitnis, Edinburgh) and Schemato (Sony AI) for showing what is currently possible with LLM-based approaches
