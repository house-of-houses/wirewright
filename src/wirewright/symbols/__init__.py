"""LTspice symbol pin geometry.

The placer and emitter both need to know where each symbol's pins sit in
canvas coordinates so that wires can terminate exactly on them. This module
is the only place that information lives.

For v0.0.1 we ship hand-curated offsets for the most common symbols. Phase 1
will verify these against the actual ``.asy`` files in the LTspice install
and add a runtime scanner for user-installed symbol libraries.
"""

from wirewright.symbols.builtin import (
    SymbolGeometry,
    absolute_pin_position,
    pin_offset,
    rotate_offset,
    symbol_geometry,
)

__all__ = [
    "SymbolGeometry",
    "absolute_pin_position",
    "pin_offset",
    "rotate_offset",
    "symbol_geometry",
]
