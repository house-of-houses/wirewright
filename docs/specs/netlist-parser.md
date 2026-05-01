# Spec: SPICE netlist parser

**Status**: draft, will be finalized in Phase 2.

## Overview

Parses a SPICE / LTspice netlist file into a `Schematic` IR with components and nets populated. Component coordinates and orientations are left as `None` for the placer to fill in.

## Scope

In scope: SPICE element cards (R, C, L, D, Q, M, V, I, X), `.SUBCKT`/`.ENDS`, `.PARAM`, `.MODEL`, `.OPTIONS`, comments. LTspice-specific directives (`.tran`, `.ac`, `.dc`, `.lib`, `.include`) preserved as raw `Schematic.directives`.

Out of scope for v0.1: hierarchy preservation (subcircuits are flattened), parameter expression evaluation (passed through as opaque strings), `.MODEL` resolution (recorded but not used by the placer), bus/vector syntax.

## Supported element types

| SPICE prefix | Mapped to symbol | Notes |
|--------------|------------------|-------|
| `R` | `res` | 2-pin resistor |
| `C` | `cap` (or `polcap` if value implies polarized) | 2-pin capacitor |
| `L` | `ind` | 2-pin inductor |
| `D` | `diode` (or `LED`, `schottky`, `zener` based on model) | 2-pin diode |
| `Q` | `npn` or `pnp` based on model | 3-pin BJT (C, B, E) |
| `M` | `nmos` or `pmos` based on model | 4-pin MOSFET (D, G, S, B) |
| `V` | `voltage` | DC, AC, PULSE, SIN, etc. |
| `I` | `current` | |
| `X` | (subcircuit, flattened) | recursively expanded |

## Subcircuit handling (v0.1: flatten)

When the parser encounters `X<name> n1 n2 ... <subckt_name>`, it:

1. Looks up the `.SUBCKT` definition by name.
2. Renames internal nets in the subcircuit to be unique (e.g. `n001` inside `LM358_inst3` becomes `LM358_inst3.n001`).
3. Maps the subcircuit's external port nets to the actual nets at the call site.
4. Inlines all the resulting components into the parent schematic.

Recursive subcircuits are supported. Self-recursion (subcircuit calls itself) is detected and rejected with a clear error.

## Net naming

- `0`, `gnd`, `GND` are normalized to net `"0"` and marked `is_ground=True`.
- Net names are case-sensitive in IR; SPICE is traditionally case-insensitive, but LTspice preserves case. We match LTspice behavior.
- Net names matching common power conventions (`vcc`, `vdd`, `vee`, `vss`, `+5V`, `-12V`, `+15V`, `-15V`, `V+`, `V-`) are auto-marked `is_power=True`. The user can override via a config flag.

## Reference designators

Every element gets the reference designator from the netlist verbatim (`R1`, `Q3`, `XU2`). For flattened subcircuits, references are prefixed with the call-site reference (e.g. `XU2.R5` becomes `U2.R5`).

## Comments and directives

Lines starting with `*` are comments and discarded.

Lines starting with `.` are directives. Recognized directives consumed by the parser (`.SUBCKT`, `.ENDS`, `.MODEL`, `.PARAM`, `.OPTIONS`). Unrecognized directives are appended verbatim to `Schematic.directives` for the emitter to write back.

Inline comments (`R1 1 2 10k ; this is a 10k resistor`) are preserved as a comment on the component if the IR ever needs them, but for v0.1 they are discarded.

## Error handling

The parser is strict by default. Malformed lines produce `ParseError` with line number and a clear message. A `--lenient` CLI flag can be added later to skip unparseable lines with a warning.

## Open questions

- Should `.MODEL` lines be parsed into structured form, or kept as raw text? v0.1: raw text. The placer does not use models.
- Should we round-trip arbitrary SPICE files exactly, or normalize them? v0.1: normalize. We promise structural equivalence, not byte-identical round-trip.
- LTspice netlists generated from `.asc` files have specific formatting quirks (e.g. `XU1` for opamp instances). We support these but do not require them.
