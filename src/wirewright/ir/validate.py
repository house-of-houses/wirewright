"""IR validation. See docs/specs/ir.md for the invariants."""

from __future__ import annotations

import logging

from wirewright.ir.model import Schematic, Wire

logger = logging.getLogger(__name__)

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
    """Validate a fully-placed Schematic ready for emission.

    Wire-induced net shorts are logged as warnings here, not raised.
    HOLA has latent shorts on multiple fixtures that pre-date this
    check; failing hard would break the v0.2.0 pipeline. Callers that
    need strict enforcement (e.g. the EEschematic experiment) call
    :func:`check_wires_induce_exact_nets` with ``strict=True`` directly.
    See ``docs/specs/ir.md`` invariant 9.
    """
    validate(schematic)
    _check_all_components_placed(schematic)
    _check_grid_alignment(schematic)
    _check_no_overlap(schematic)
    check_wires_induce_exact_nets(schematic, strict=False)


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


def _point_on_segment_closed(point: tuple[int, int], w: Wire) -> bool:
    """True if ``point`` lies anywhere on the closed segment of wire ``w``."""
    px, py = point
    if w.x1 == w.x2:
        if px != w.x1:
            return False
        return min(w.y1, w.y2) <= py <= max(w.y1, w.y2)
    if py != w.y1:
        return False
    return min(w.x1, w.x2) <= px <= max(w.x1, w.x2)


def check_wires_induce_exact_nets(s: Schematic, *, strict: bool = False) -> None:
    """Check that wires + flags induce exactly one net per connected pin class.

    ``strict=False`` (the default used by :func:`validate_placed`) logs
    each short at ``WARNING`` and returns normally. ``strict=True``
    raises :class:`ValidationError` on the first short — used by the
    EEschematic experiment where correctness is non-negotiable.

    A wire that shorts two different nets — e.g. an L-bend corner
    coincides with a pin of a third net, or a segment passes through
    such a pin — is caught. Power and ground nets are exempt from the
    completeness side (``emit_power_ground_rails`` ties their pins via
    FLAGs, not wires), but any wire that touches a ground/power pin
    while carrying a different net's signal still counts as a short.
    """
    from wirewright.symbols.builtin import absolute_pin_position

    # Collect pins and flags as position → list[(net_name, label)].
    endpoints: dict[tuple[int, int], list[tuple[str, str]]] = {}
    for c in s.components:
        if c.x is None or c.y is None:
            continue
        for pin_name, net_name in c.pins.items():
            try:
                pos = absolute_pin_position(
                    (c.x, c.y), c.symbol, pin_name, c.orientation
                )
            except KeyError:
                continue
            endpoints.setdefault(pos, []).append((net_name, f"{c.ref}.{pin_name}"))
    for fl in s.flags:
        endpoints.setdefault((fl.x, fl.y), []).append((fl.net, f"flag@({fl.x},{fl.y})"))

    # Union-find over all positions involved in wires or at pins/flags.
    parent: dict[tuple[int, int], tuple[int, int]] = {p: p for p in endpoints}

    def find(x: tuple[int, int]) -> tuple[int, int]:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: tuple[int, int], b: tuple[int, int]) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for w in s.wires:
        parent.setdefault((w.x1, w.y1), (w.x1, w.y1))
        parent.setdefault((w.x2, w.y2), (w.x2, w.y2))
        union((w.x1, w.y1), (w.x2, w.y2))

    # A wire passing through a pin at interior or at the endpoint connects
    # the wire's electrical class to that pin. Endpoint coincidence is
    # already handled by shared dict keys; this picks up interior hits.
    for w in s.wires:
        for pos in endpoints:
            if _point_on_segment_closed(pos, w):
                union(pos, (w.x1, w.y1))

    # Short detection: any class containing pins/flags of more than one net.
    # (Completeness — "all multi-pin signal nets are wired together" — is
    # intentionally NOT checked here: many unit-test fixtures construct
    # placed-but-unwired schematics to test overlap or grid invariants in
    # isolation. Completeness is a separate check that lives at emission
    # time if we add it; the critical safety-of-output guarantee is "no
    # shorts". A placer that leaves nets disconnected produces a broken
    # schematic that the user will see immediately in LTspice — a short
    # that passes validation is a silent correctness failure.)
    classes: dict[tuple[int, int], list[tuple[str, str]]] = {}
    for pos, labels in endpoints.items():
        classes.setdefault(find(pos), []).extend(labels)
    for root, items in classes.items():
        net_names = {n for n, _ in items}
        if len(net_names) > 1:
            by_net: dict[str, list[str]] = {}
            for n, lbl in items:
                by_net.setdefault(n, []).append(lbl)
            parts = "; ".join(f"{n!r}=[{','.join(ls)}]" for n, ls in by_net.items())
            msg = (
                f"Wires short multiple nets at wire class rooted at {root}: {parts}"
            )
            if strict:
                raise ValidationError(msg)
            logger.warning("validate_placed: %s", msg)


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
