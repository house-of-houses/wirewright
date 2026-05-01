# Spec: SPICE netlist parser

**Status**: draft, will be finalized in Phase 2.

## Overview

Parses a SPICE / LTspice netlist file into a `Schematic` IR with components and nets populated. Component coordinates and orientations are left as `None` for the placer to fill in.

## Scope

In scope: SPICE element cards (R, C, L, D, Q, M, V, I, B, E, F, G, H, X), `.SUBCKT`/`.ENDS`, `.PARAM`, `.MODEL`, `.OPTIONS`, comments, `+` line continuations. LTspice-specific directives (`.tran`, `.ac`, `.dc`, `.lib`, `.include`, `.meas`) preserved as raw `Schematic.directives`.

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
| `B` | `bv` (V=expr) or `bi` (I=expr) | 2-pin behavioral source |
| `E` | `e` | 4-pin VCVS: out+, out-, ctrl+, ctrl- |
| `G` | `g` | 4-pin VCCS, same pin order as E |
| `F` | `f` | CCCS (current-controlled current source) |
| `H` | `h` | CCVS (current-controlled voltage source) |
| `X` | (subcircuit, flattened) | recursively expanded |
| `S` | `sw` | 4-pin voltage-controlled switch |

### v0.1 limitations

- 4-node Q cards (BJTs with explicit substrate node) raise `ParseError`. Use the 3-node form `Q<ref> nc nb ne <model>`.
- Local `.MODEL` declarations inside `.SUBCKT` bodies raise `ParseError`. Declare models at top level.
- LED/Zener/Schottky discrimination from `.MODEL D(...)` parameters is deferred; every `D` card maps to symbol `diode` regardless of model parameters.

## IR pin names per element

The IR `Component.pins` dict maps an *IR pin name* to a net. The IR pin names
match the corresponding `.asy` file's `PINATTR PinName` whenever the symbol
has a clear convention; otherwise SpiceOrder index is used. This lets the
emitter look up the offset in `wirewright.symbols.builtin` without an extra
mapping layer.

| Element | SPICE card form | IR pin names |
|---------|-----------------|--------------|
| `R`/`C`/`L` | `<ref> n1 n2 value` | `"1"`, `"2"` |
| `D` | `<ref> n+ n- model` | `"A"` (anode), `"K"` (cathode) |
| `Q` | `<ref> nc nb ne model` | `"C"`, `"B"`, `"E"` |
| `M` | `<ref> nd ng ns nb model` | `"D"`, `"G"`, `"S"`, `"B"` |
| `V`/`I` | `<ref> n+ n- value` | `"+"`, `"-"` |
| `B` | `<ref> n+ n- V=expr` *or* `I=expr` | `"+"`, `"-"` |
| `E`/`G` | `<ref> n+ n- nc+ nc- gain` | `"+"`, `"-"`, `"P"`, `"N"` |
| `S` | `<ref> n+ n- nc+ nc- model` | `"A"`, `"B"`, `"NC+"`, `"NC-"` (matches `sw.asy`) |

The full `B` card body after the `<ref> n+ n-` prefix (including `V=` or `I=`
and the entire arbitrary expression, with continuations joined) is preserved
verbatim in `Component.value`. The emitter writes it back unchanged.

## Line continuations

A line whose first non-whitespace character is `+` is a continuation of the
previous logical line. Continuations are joined with a single space before
tokenization. This is the SPICE convention and is required for behavioral
sources and any other element whose value spans multiple lines.

```
B_GATE GATE 0 V=5*(
+ (time>=0 & time<50m) +
+ (time>=500m & time<600m))
```

becomes one logical line equivalent to:

```
B_GATE GATE 0 V=5*( (time>=0 & time<50m) + (time>=500m & time<600m))
```

before parsing. Comment lines (`*`) are skipped *before* continuation joining,
so a `*` between continuations does not break the chain. Blank lines do break
the chain.

## Subcircuit handling (v0.1: flatten)

When the parser encounters `X<ref> n1 ... nN <subckt_name>`, it:

1. Looks up the `.SUBCKT` definition by name.
2. Constructs a namespace prefix from `ref[1:] + "."` — i.e., the leading `X` is stripped, then a dot is appended (e.g. `XU2` → `U2.`, `XU_SQR` → `U_SQR.`).
3. Renames every internal subckt component reference and internal net by prepending the prefix (`R5` inside the subckt → `U2.R5`; internal net `n001` → `U2.n001`).
4. Maps subckt external port nets to the call-site nets (port `IN+` → call-site arg 1, etc.). The literal nets `0` and `gnd` are normalized to `0` regardless of the namespace.
5. Inlines all the resulting components into the parent schematic.

Recursive subcircuits are supported (a subckt may instantiate other subckts). Self-recursion — a subckt calling itself, directly or transitively through any chain — is rejected with `ParseError`. Nested `.SUBCKT` definitions and unclosed `.SUBCKT` blocks are also rejected with `ParseError`.

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
