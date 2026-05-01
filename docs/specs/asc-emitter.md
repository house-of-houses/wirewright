# Spec: LTspice .asc emitter

**Status**: draft, will stabilize in Phase 1.

## Overview

The ASC emitter takes a fully-placed `Schematic` (every component has coordinates and orientation; wires are populated) and writes an LTspice `.asc` file that opens cleanly in LTspice with all connections electrically valid.

## Scope

In scope: serialization of an IR `Schematic` to `.asc` syntax, grid snapping, orientation encoding, FLAG/SYMATTR/WIRE/SYMBOL/TEXT lines.

Out of scope: producing the placement (placer concern), parsing `.asc` (parser concern), generating new `.asy` symbols.

## Output file format

LTspice `.asc` is line-based plain text. The first line is always:

```
Version 4
SHEET 1 N N
```

Where `N N` is the canvas width and height in grid units (typically `880 680` for default sheet, larger for bigger schematics; the emitter computes the bounding box of all elements plus a margin).

## Line types we emit

### `WIRE x1 y1 x2 y2`

Axis-aligned wire segment. x1, y1, x2, y2 are integers, multiples of 16.

### `FLAG x y name`

Net label at a point. Special case: `name == "0"` produces a GND symbol. Otherwise produces an IO label (with text `name`).

### `IOPIN x y direction`

Hierarchical pin marker. Not used in v0.1 (no hierarchy).

### `SYMBOL libname x y orientation`

Place a symbol from the LTspice library. `libname` is the symbol name without `.asy` (e.g. `res`, `npn`, `Opamps/opamp2`). `x`, `y` is the symbol's origin in grid units. `orientation` is one of `R0 R90 R180 R270 M0 M90 M180 M270`.

### `SYMATTR Key Value`

Attribute on the most recently placed `SYMBOL`. Common keys:
- `InstName`: the reference designator (R1, Q3, U2)
- `Value`: the human label (10k, 1n, LM358)
- `SpiceModel`: the model name for transistors etc.
- `Prefix`: the SPICE letter prefix (R, C, L, Q, M, D)

### `TEXT x y Left|Right|Center 2 ;text` and `TEXT x y Left 2 !.directive`

Text annotations and SPICE directives. Directives start with `!`, comments with `;`. Used for `.tran`, `.ac`, `.model`, `.lib`.

## Coordinate transformation

The IR stores integer coordinates where 1 unit = 1 mil. The `.asc` file uses the same units: every coordinate emitted is an integer, and every position must be a multiple of 16 (the LTspice grid).

The emitter validates this invariant. Any non-multiple-of-16 coordinate raises `EmitterError` with a clear message naming the offending element.

## Pin attachment

Wires connect to component pins by terminating exactly on the pin's absolute position in the canvas. The pin's absolute position is:

```
absolute_pos = component_origin + rotate(pin_offset, orientation)
```

Where `pin_offset` comes from `wirewright.symbols.builtin.pin_offset(symbol, pin_name)` and `rotate` applies the orientation transform around the symbol's origin.

If a wire endpoint does not exactly match a pin's absolute position (for endpoints intended to attach), LTspice will display them as disconnected even though they look close. The emitter must therefore snap wire endpoints to pin positions where the placer intended a connection.

## Output ordering

For deterministic diffs:
1. WIRE lines, sorted by (x1, y1, x2, y2).
2. FLAG lines, sorted by (x, y, net).
3. SYMBOL blocks (each followed by its SYMATTR lines), sorted by component reference designator (R1, R2, ..., R10 → R1 R10 R2 with naive sort, so use natural sort on numeric suffix).
4. TEXT lines, in the order they appeared in the input directives (preserves user intent).

## Open questions

- Are there `.asc` files that round-trip through this emitter and produce a binary-different but semantically-equivalent file? Probably yes; we accept this for v0.1 but may add a normalization step later.
- LTspice supports both ASCII and binary `.asc` for very old versions. We only emit ASCII v4.
