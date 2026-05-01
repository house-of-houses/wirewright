"""LTspice .asc file emitter. See docs/specs/asc-emitter.md.

The minimum-viable emitter shipped in v0.0.1 covers everything needed for
the demo and the simpler fixtures. Phase 1 will harden it for the full
symbol set and edge cases.
"""

from __future__ import annotations

import re
from pathlib import Path

from wirewright.ir.model import Schematic
from wirewright.ir.validate import LTSPICE_GRID, validate_placed
from wirewright.symbols import symbol_geometry


class EmitterError(Exception):
    """Raised when a Schematic cannot be serialized to a valid .asc file."""


SHEET_MARGIN = 16 * 8


def emit_asc(schematic: Schematic) -> str:
    """Serialize a placed Schematic to .asc text.

    Validates placement before emitting; raises ``ValidationError`` if any
    invariant fails.
    """
    validate_placed(schematic)
    lines: list[str] = []

    # Sheet header. Width and height computed from bounding box.
    width, height = _compute_sheet_size(schematic)
    lines.append("Version 4")
    lines.append(f"SHEET 1 {width} {height}")

    # Wires (deterministic order).
    for w in sorted(schematic.wires, key=lambda w: (w.x1, w.y1, w.x2, w.y2)):
        lines.append(f"WIRE {w.x1} {w.y1} {w.x2} {w.y2}")

    # Flags.
    for fl in sorted(schematic.flags, key=lambda f: (f.x, f.y, f.net)):
        lines.append(f"FLAG {fl.x} {fl.y} {fl.net}")

    # Symbols, sorted by reference designator with natural numeric ordering.
    for c in sorted(schematic.components, key=lambda c: _natural_sort_key(c.ref)):
        # We already verified pin offsets exist for c.symbol via validate_placed,
        # but double-check at emission time to avoid silent file corruption.
        try:
            symbol_geometry(c.symbol)
        except KeyError as e:
            raise EmitterError(
                f"Component {c.ref!r}: unknown symbol {c.symbol!r}. "
                f"Add geometry to wirewright.symbols.builtin."
            ) from e

        lines.append(f"SYMBOL {c.symbol} {c.x} {c.y} {c.orientation}")
        lines.append(f"SYMATTR InstName {c.ref}")
        if c.value:
            lines.append(f"SYMATTR Value {c.value}")
        if c.spice_model:
            lines.append(f"SYMATTR SpiceModel {c.spice_model}")
        if c.spice_prefix and c.spice_prefix not in {"R", "C", "L", "V", "I", "D", "Q", "M"}:
            # Standard prefixes are inferred by LTspice from the symbol; emit
            # only non-standard prefix overrides.
            lines.append(f"SYMATTR Prefix {c.spice_prefix}")

    # Directives and comments.
    directive_y = height - SHEET_MARGIN
    for i, directive in enumerate(schematic.directives):
        kind = "!" if directive.startswith(".") else ";"
        body = directive.lstrip(". ;") if kind == "!" else directive
        text = directive if kind == "!" else body
        lines.append(f"TEXT {SHEET_MARGIN} {directive_y + i * 32} Left 2 {kind}{text}")

    return "\n".join(lines) + "\n"


def write_asc(schematic: Schematic, path: str | Path) -> None:
    """Convenience wrapper: emit to text and write to disk."""
    Path(path).write_text(emit_asc(schematic))


def _compute_sheet_size(s: Schematic) -> tuple[int, int]:
    """Compute SHEET width and height from the bounding box of all elements."""
    xs: list[int] = []
    ys: list[int] = []
    for c in s.components:
        if c.x is not None and c.y is not None:
            geo = symbol_geometry(c.symbol)
            xs.extend([c.x + geo.bbox[0], c.x + geo.bbox[2]])
            ys.extend([c.y + geo.bbox[1], c.y + geo.bbox[3]])
    for w in s.wires:
        xs.extend([w.x1, w.x2])
        ys.extend([w.y1, w.y2])
    for f in s.flags:
        xs.append(f.x)
        ys.append(f.y)

    if not xs or not ys:
        # Empty schematic: minimum sheet.
        return (880, 680)

    width = max(xs) + SHEET_MARGIN
    height = max(ys) + SHEET_MARGIN
    # Round up to grid.
    width = ((width + LTSPICE_GRID - 1) // LTSPICE_GRID) * LTSPICE_GRID
    height = ((height + LTSPICE_GRID - 1) // LTSPICE_GRID) * LTSPICE_GRID
    return (width, height)


_NATURAL_RE = re.compile(r"(\d+)")


def _natural_sort_key(s: str) -> list[str]:
    """Sort 'R10' after 'R2'; type-stable across refs that start with digits.

    Numeric runs are zero-padded so lexicographic comparison gives natural
    ordering. Returning a uniform ``list[str]`` avoids ``TypeError`` when
    flattened-subckt refs like ``"1.B_OTA"`` start with a digit (would
    otherwise mix int and str in the key list).
    """
    return [t.zfill(8) if t.isdigit() else t.lower() for t in _NATURAL_RE.split(s) if t]
