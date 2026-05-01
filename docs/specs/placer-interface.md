# Spec: Placer interface

**Status**: stable in v0.1.

## Overview

A `Placer` consumes an unplaced `Schematic` (every `Component` has `x = y = None`) and returns a fully-placed `Schematic` (every `Component` has integer `x`, `y`, `orientation`, and `Schematic.wires` is populated with axis-aligned wires that connect the right pins).

## The contract

```python
from abc import ABC, abstractmethod
from wirewright.ir.model import Schematic

class Placer(ABC):
    """Abstract base for all placement back ends."""

    name: str        # short identifier used by the CLI: "naive", "elk", "hola"

    @abstractmethod
    def place(self, schematic: Schematic, hints: dict | None = None) -> Schematic:
        """Return a new Schematic with placement and routing populated.

        Must not mutate the input.

        Hints are placer-specific. Unknown hints are silently ignored.
        Common hints all placers should support:
            - "direction": "LR" | "RL" | "TB" | "BT" (signal flow direction)
            - "aspect_ratio": float (target width/height)
            - "pinned": dict[str, tuple[int, int, str]] (component ref → (x, y, orientation))
        """
```

## Required behavior

- **Pure**: must not mutate the input `Schematic`. Returns a new one.
- **Total**: must place every component, even if the result is ugly. Throwing an error is only acceptable for genuinely impossible inputs (cycles in pinned constraints, missing symbol pin data).
- **Validating**: the returned `Schematic` must pass `ir.validate.validate_placed(schematic)`.
- **Deterministic**: same input + same hints = same output. (Random seeds, if used internally, must be fixed by the back end.)
- **Grid-snapped**: every coordinate is a multiple of 16.
- **Connecting**: every wire endpoint that the placer intended as a connection sits exactly on a component pin's absolute position. The emitter does not fix up imprecise endpoints.

## Power and ground handling

Nets marked `is_power` or `is_ground` are NOT routed as ordinary edges. The placer:

1. Identifies these nets up front.
2. Decides on a global rail strategy (typically: ground on the bottom of the canvas, V+ on the top, V- below V+).
3. Emits FLAG entries (via `Schematic.flags`) at each component pin connecting to a power/ground rail, rather than long wires across the canvas.

This applies to all back ends.

## Hints recognized by specific back ends

### naive
- Does not recognize any hints. Lays out in input order on a regular grid.

### elk
- `direction`: maps to `elk.direction` (LR→RIGHT, RL→LEFT, TB→DOWN, BT→UP). Default RIGHT.
- `aspect_ratio`, `pinned`: not yet supported in v0.1; ignored silently. v0.3+.

ELK uses Eclipse Layout Kernel via a Node.js subprocess (`tools/elk-bridge/`).
Failure modes specific to ELK:
- `node` not on PATH → `PlacerEngineError` with install instructions.
- `tools/elk-bridge/node_modules/` missing → `PlacerEngineError`.
- ELK subprocess timeout (default 30s) → `PlacerEngineError`.
- ELK rejects the graph (e.g., port-constraint violation) → `PlacerEngineError` wrapping the bridge's stderr.

### hola
- Does not recognize `direction`, `aspect_ratio`, or `pinned` in v0.1 (HOLA is unconstrained stress-majorization). Hints are silently ignored.
- Requires the optional `hola` extra: `uv sync --extra hola`.
- Disconnected non-power/ground graphs are stitched with virtual edges before layout (HOLA aborts on disconnected input).
- Non-planar graphs raise `PlacerEngineError` with a suggestion to use `--placer elk`.
- Some planar graphs still trigger HOLA's internal `faces.cpp:identifyExternalFace` C++ assertion, which Python cannot catch. Subprocess isolation is deferred to v0.2; meanwhile, fixtures that crash HOLA need ELK or naive.

## Failure modes

| Condition | Behavior |
|-----------|----------|
| Component references a pin not in `symbols.builtin` | raise `PlacerError` with the symbol/pin name |
| Pinned constraints in `hints["pinned"]` form a cycle | raise `PlacerError` |
| Underlying engine fails (Node bridge crash, pyhola exception) | raise `PlacerEngineError` wrapping the original |
| Engine produces output where pins do not align to the grid | snap with a warning logged at INFO level |
| Engine produces overlapping components | raise `PlacerError`; the engine should have prevented this |

## Test parametrization

Every placer is tested against the same suite of generic placement tests (`tests/unit/test_placers.py::TestAnyPlacer`). New back ends are added to the test parametrization automatically.

## Open questions

- Should placers expose a `quality_estimate(schematic) -> float` method so the CLI can auto-pick the best one? Probably not for v0.1: explicit `--placer` is fine.
- Do we want a `place_with_progress(...)` async variant for large circuits? v0.1: no; circuits are small enough.
