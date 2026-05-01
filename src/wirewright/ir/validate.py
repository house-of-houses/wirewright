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
    """Approximate check: no two components share an exact origin.

    A real overlap check needs symbol bounding boxes, which the symbols module
    will provide. For v0.0.1 this catches the most obvious bugs.
    """
    seen: dict[tuple[int, int], str] = {}
    for c in s.components:
        if c.x is None or c.y is None:
            continue
        key = (c.x, c.y)
        if key in seen:
            raise ValidationError(
                f"Components {seen[key]!r} and {c.ref!r} placed at the same origin ({c.x}, {c.y})"
            )
        seen[key] = c.ref
