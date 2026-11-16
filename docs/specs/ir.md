# Spec: Internal Representation (IR)

**Status**: stable in v0.1.

## Overview

The IR is the data structure every internal module reads and writes. It is the stable contract that decouples parsing, placement, pattern matching, routing, and emission.

## Scope

In scope: data shape, invariants, validation rules, coordinate system.

Out of scope: how the IR is produced (parser concern), how it is consumed (placer/emitter concern), persistence format (debug-only JSON dump is fine).

## Coordinate system

All coordinates are integers in LTspice grid units. One grid unit equals 16 mils in the LTspice canvas (this matches what LTspice writes natively in `.asc` files: every coordinate visible in an `.asc` file is a multiple of 16, and we store the underlying integer where 1 = 1 mil).

The origin is the top-left of the canvas. X increases to the right. Y increases downward. (This matches LTspice's native convention.)

Floating-point coordinates anywhere in the IR are a bug.

## Types

### `Pin`

```python
@dataclass(frozen=True)
class Pin:
    name: str                    # "+", "-", "OUT", "1", "2", "B", "C", "E", ...
    side: Literal["N","E","S","W"] | None = None  # optional layout hint
```

### `Component`

```python
@dataclass
class Component:
    ref: str                     # designator: "R1", "Q3", "U2"
    symbol: str                  # LTspice symbol name: "res", "npn", "opamp2"
    value: str | None = None     # human label: "10k", "1n", "LM358"
    pins: dict[str, str] = ...   # pin_name → net_name
    # populated by placer:
    x: int | None = None
    y: int | None = None
    orientation: Orientation = "R0"
```

`Orientation` is one of `R0, R90, R180, R270, M0, M90, M180, M270` (the eight LTspice symbol orientations: four rotations and four mirror-rotations).

### `Net`

```python
@dataclass
class Net:
    name: str                    # "vin", "vout", "n001", "0", "vcc"
    is_power: bool = False       # routed as a global rail
    is_ground: bool = False      # routed as a global rail; net name "0" forces this
```

### `Wire`

```python
@dataclass
class Wire:
    x1: int; y1: int
    x2: int; y2: int
```

Wires are always axis-aligned: either x1 == x2 (vertical) or y1 == y2 (horizontal). Diagonal wires are a bug.

### `Schematic`

```python
@dataclass
class Schematic:
    components: list[Component]
    nets: list[Net]
    wires: list[Wire] = []
    flags: list[Flag] = []       # net labels at specific points
    directives: list[str] = []   # raw SPICE directives (.tran, .ac, .model, ...)
```

### `Flag`

```python
@dataclass(frozen=True)
class Flag:
    x: int
    y: int
    net: str                     # "0" → GND symbol, otherwise → IO label
```

## Invariants

These are enforced by `ir.validate.validate(schematic)`:

1. Every `Component.pins[pin_name]` references a `Net.name` that exists in `Schematic.nets`.
2. Every component reference (`ref`) is unique within the schematic.
3. Every net referenced by any component pin appears in `Schematic.nets`.
4. After placement, every `Component` has non-None `x`, `y`, `orientation`.
5. After placement, every `Wire` endpoint sits on the LTspice grid (multiple of 16).
6. After placement, no two component bounding boxes overlap.
7. Pin absolute positions are guaranteed to lie on the grid by construction: invariant 5 (component on grid) plus the registration-time assertion in `wirewright.symbols.builtin._assert_pin_offsets_grid_aligned` that every registered pin offset is a multiple of `LTSPICE_GRID`. Not separately checked at runtime in `validate_placed`.
8. The net `"0"` (and any net with `is_ground=True`) is always treated as ground.
9. After placement, no wire should short two different nets. Two pins of
   different nets must not share a union-find class reached via wire
   endpoints and wire-interior crossings. Checked by
   `ir.validate.check_wires_induce_exact_nets`. `validate_placed` calls it
   with `strict=False` and logs any short as a `WARNING` — HOLA has
   latent shorts on multiple fixtures that pre-date this check, and
   failing hard would break the v0.2.0 pipeline. The EEschematic
   experiment (and other callers that need correctness guarantees) call
   the function with `strict=True`, raising `ValidationError` on the
   first short. Ground and power nets are exempt from the completeness
   side (their pins are tied by FLAGs via rails, not wires), but any
   wire that touches a ground/power pin while carrying a different
   net's signal still counts as a short. Routers must treat pins of
   other nets as point obstacles when picking L-bend corners — see
   `routing.orthogonal.route_avoiding(..., pin_obstacles=...)`.

## What the IR does not capture (yet)

- Hierarchy: subcircuits are flattened by the parser. Hierarchy may come back in v0.2+.
- Layered/multi-page schematics: out of scope for v0.1.
- Bus/vector nets: not relevant for analog. Out of scope.

## Versioning

The IR is internal, not persisted. We do not version it. If you change the dataclass shapes, every other module must update. Since v0.x is pre-stable, this is acceptable. Post-1.0, IR changes will be ADR-tracked.

## Round-trip lossy properties

The IR ↔ `.asc` boundary preserves connectivity and component placement, but
the following are NOT preserved across `emit_asc → parse_asc_text`:

- `Net.is_power` flagging — there is no `.asc` convention to mark a net as
  power, so all parsed nets have `is_power=False`.
- `Schematic.nets` ordering — the emitter does not write nets explicitly;
  the parser builds them in pin-iteration order.
- `Component.spice_prefix` for standard prefixes (R/C/L/V/I/D/Q/M) — the
  emitter only writes `SYMATTR Prefix` for non-standard prefixes since
  LTspice infers standard ones from the symbol.
- Free `TEXT` comments (`;`-prefixed) — no IR field in v0.1.

## Open questions

Per ADR-0002, post-1.0 IR changes will be tracked by superseding ADRs. Both
pin-direction hints (for opamp `+/-/OUT` signal flow) and signal-kind tags
(audio/CV/gate) remain unscoped for v0.1; revisit if the pattern library
needs them.
