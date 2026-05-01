"""IR validation. See docs/specs/ir.md for the invariants."""

from __future__ import annotations

from wirewright.ir.model import Schematic

LTSPICE_GRID = 16
"""LTspice canvas grid size in IR units. All coordinates must be a multiple."""


class ValidationError(Exception):
    """Raised when an IR Schematic violates a documented invariant."""


def validate(schematic: Schematic) -> None:
    """Validate a Schematic that may or may not be placed.

    Checks structural invariants only (component refs unique, every pin's net
    exists, every component reference's pin nets are declared).

    Use :func:`validate_placed` for the stronger post-placement invariants.
    """
    _check_unique_refs(schematic)
    _check_pin_nets_declared(schematic)


def validate_placed(schematic: Schematic) -> None:
    """Validate a fully-placed Schematic ready for emission."""
    validate(schematic)
    _check_all_components_placed(schematic)
    _check_grid_alignment(schematic)
    _check_no_overlap(schematic)


def _check_unique_refs(s: Schematic) -> None:
    seen: set[str] = set()
    for c in s.components:
        if c.ref in seen:
            raise ValidationError(f"Duplicate component reference: {c.ref!r}")
        seen.add(c.ref)


def _check_pin_nets_declared(s: Schematic) -> None:
    declared = {n.name for n in s.nets}
    for c in s.components:
        for pin_name, net_name in c.pins.items():
            if net_name not in declared:
                raise ValidationError(
                    f"Component {c.ref}: pin {pin_name!r} references undeclared net {net_name!r}"
                )


def _check_all_components_placed(s: Schematic) -> None:
    for c in s.components:
        if not c.is_placed:
            raise ValidationError(f"Component {c.ref!r} has no coordinates after placement")


def _check_grid_alignment(s: Schematic) -> None:
    for c in s.components:
        if c.x is not None and c.x % LTSPICE_GRID != 0:
            raise ValidationError(
                f"Component {c.ref!r} x={c.x} not on LTspice grid (multiple of {LTSPICE_GRID})"
            )
        if c.y is not None and c.y % LTSPICE_GRID != 0:
            raise ValidationError(
                f"Component {c.ref!r} y={c.y} not on LTspice grid (multiple of {LTSPICE_GRID})"
            )
    for w in s.wires:
        for label, val in [("x1", w.x1), ("y1", w.y1), ("x2", w.x2), ("y2", w.y2)]:
            if val % LTSPICE_GRID != 0:
                raise ValidationError(f"Wire endpoint {label}={val} not on grid: {w}")
    for fl in s.flags:
        if fl.x % LTSPICE_GRID != 0 or fl.y % LTSPICE_GRID != 0:
            raise ValidationError(f"Flag {fl} not on grid")


def _check_no_overlap(s: Schematic) -> None:
    """Reject any pair of components whose oriented bounding boxes overlap."""
    from wirewright.symbols.builtin import rotate_offset, symbol_geometry

    placed: list[tuple[str, tuple[int, int, int, int]]] = []
    for c in s.components:
        if c.x is None or c.y is None:
            continue
        try:
            geo = symbol_geometry(c.symbol)
        except KeyError:
            continue  # unknown symbol — caught elsewhere
        x1, y1, x2, y2 = geo.bbox
        # Rotate the four bbox corners around the symbol origin and re-min/re-max
        # to handle non-R0 orientations (including the four mirror variants).
        corners = [
            rotate_offset((x1, y1), c.orientation),
            rotate_offset((x2, y1), c.orientation),
            rotate_offset((x1, y2), c.orientation),
            rotate_offset((x2, y2), c.orientation),
        ]
        rxs = [p[0] for p in corners]
        rys = [p[1] for p in corners]
        bbox = (c.x + min(rxs), c.y + min(rys), c.x + max(rxs), c.y + max(rys))
        placed.append((c.ref, bbox))

    for i, (ref_a, a) in enumerate(placed):
        for ref_b, b in placed[i + 1 :]:
            # Touching edges are not overlap; strict less-than.
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                raise ValidationError(f"Components {ref_a!r} and {ref_b!r} bounding boxes overlap")
