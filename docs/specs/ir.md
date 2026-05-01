# Spec: Internal Representation (IR)

**Status**: draft, will stabilize in Phase 1.

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
7. After placement, every component pin's absolute position (computed from `x`, `y`, `orientation`, and the symbol's pin offset) lies on the grid.
8. The net `"0"` (and any net with `is_ground=True`) is always treated as ground.

## What the IR does not capture (yet)

- Hierarchy: subcircuits are flattened by the parser. Hierarchy may come back in v0.2+.
- Layered/multi-page schematics: out of scope for v0.1.
- Bus/vector nets: not relevant for analog. Out of scope.

## Versioning

The IR is internal, not persisted. We do not version it. If you change the dataclass shapes, every other module must update. Since v0.x is pre-stable, this is acceptable. Post-1.0, IR changes will be ADR-tracked.

## Open questions

- Should `Component` carry a `pin_directions` hint to inform the placer about signal flow? Likely yes for opamp `+/-/OUT`. Decided in Phase 3.
- Should `Net` carry a `signal_kind` (audio, CV, gate, clock)? Probably not for v0.1; revisit if the pattern library needs it.
