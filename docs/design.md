# wirewright architecture

## Pipeline

```
┌──────────────┐   ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ SPICE netlist│──▶│  parse  │──▶│    IR    │──▶│ patterns │──▶│  placer  │
└──────────────┘   └─────────┘   └──────────┘   │  (opt.)  │   │ (adapter)│
                                                └──────────┘   └────┬─────┘
                                                                    │
                                                                    ▼
                                ┌──────────────────────────┐
                                │ IR with x/y/orientation  │
                                │ + wires from routing     │
                                └─────────────┬────────────┘
                                              │
                                              ▼
┌──────────────┐   ┌─────────┐   ┌──────────────────────────┐
│   .asc file  │◀──│ ASC     │◀──│       routing            │
└──────────────┘   │ emitter │   │  (orthogonal wires)      │
                   └─────────┘   └──────────────────────────┘
```

## Key invariants

- The IR (`src/wirewright/ir/model.py`) is the only data format that crosses module boundaries internally. Everything else converts to/from IR at the edges.
- Coordinates inside the IR are integers in LTspice grid units (16 mil per unit). No floating-point coordinates ever live in the IR.
- A `Placer` consumes a `Schematic` with empty coordinates and returns a `Schematic` with all `Component.x`, `Component.y`, `Component.orientation` and `Schematic.wires` populated.
- Symbol pin offsets only live in `src/wirewright/symbols/`. Anything that needs to know "where does pin B of an NPN sit relative to its origin under R90?" asks the symbols module.

## Module responsibilities

| Module | Knows about | Does NOT know about |
|--------|-------------|---------------------|
| `parse/spice.py` | SPICE syntax, device prefixes | placement, file output |
| `parse/ltspice_asc.py` | `.asc` syntax, LTspice grid | placement strategy |
| `ir/model.py` | data shape | parsing, placement, output |
| `ir/validate.py` | invariants on IR | how IR is produced |
| `placers/base.py` | the contract | any specific placer |
| `placers/hola.py` | HOLA ↔ IR translation, hola-graph subprocess | other placers, file output |
| `patterns/matcher.py` | subgraph isomorphism | specific symbols |
| `patterns/library/*.yaml` | one analog idiom each | the matcher mechanics |
| `routing/orthogonal.py` | wire routing on grid | placement |
| `symbols/builtin.py` | pin offsets for stock symbols | placement, file output |
| `emit/asc.py` | `.asc` file format | parsing, placement |
| `cli.py` | UX | implementation details |

## Why these dependencies and not others

Python is the host language because the pattern library, fixture management, and symbol metadata all live more naturally in Python than in JavaScript or Java. HOLA is reached through `hola-graph` (the renamed `pyhola`, a pybind11 wrapper around adaptagrams) which ships ARM64 macOS / Linux x86_64 PyPI wheels. The actual `layout()` call runs in a subprocess so HOLA's C++ asserts (in `faces.cpp::identifyExternalFace` for certain graph topologies) don't kill the parent Python process.

NetworkX provides subgraph isomorphism (VF2) without C++ build pain. If matching becomes a bottleneck on large circuits, we replace it with a wrapped VF3.

## What's NOT in this architecture

No GUI. No LLM in the core (could be a side experiment). No PCB layout. No symbol generation. No hierarchy in the IR for v0.1 (subcircuits are flattened by the parser).
