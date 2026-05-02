"""Power/ground rail synthesis.

After component placement, ground/power nets get drawn as global horizontal
rails (top of canvas for power, bottom for ground) instead of as scattered
FLAGs on individual pins. This is the v0.2 quality fix: scattered ground
flags are visually noisy, especially on transistor-heavy schematics where
every emitter has its own little FLAG cluster.

Per :doc:`docs/specs/placer-interface.md` "Power and ground handling": every
placer back end emits these as global rails, not as ordinary edges.
"""

from __future__ import annotations

from collections import defaultdict

from wirewright.ir.model import Component, Flag, Schematic, Wire
from wirewright.ir.validate import LTSPICE_GRID
from wirewright.symbols.builtin import absolute_pin_position

_RAIL_OFFSET = LTSPICE_GRID * 4
"""Distance from the canvas extremum to the rail itself."""


def emit_power_ground_rails(schematic: Schematic) -> tuple[list[Wire], list[Flag]]:
    """Compute rail wires + FLAGs for every power/ground net.

    Returns ``(extra_wires, extra_flags)``. Caller appends them to the
    schematic. Skips silently when the schematic has no placed components,
    no nets, or no power/ground membership.
    """
    if not schematic.components:
        return [], []

    placed = [c for c in schematic.components if c.x is not None and c.y is not None]
    if not placed:
        return [], []

    nets_by_name = {n.name: n for n in schematic.nets}

    # Group pins by ground vs power net.
    ground_pins: dict[str, list[tuple[int, int]]] = defaultdict(list)
    power_pins: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for c in placed:
        for pin_name, net_name in c.pins.items():
            net = nets_by_name.get(net_name)
            if net is None:
                continue
            assert c.x is not None and c.y is not None
            pos = absolute_pin_position((c.x, c.y), c.symbol, pin_name, c.orientation)
            if net.is_ground or net.name == "0":
                ground_pins["0"].append(pos)
            elif net.is_power:
                power_pins[net.name].append(pos)

    if not ground_pins and not power_pins:
        return [], []

    # Canvas extent — used to position the rails outside all component bodies.
    min_y, max_y = _component_y_extent(placed)

    extra_wires: list[Wire] = []
    extra_flags: list[Flag] = []

    # Ground rail: below the lowest component.
    for net_name, positions in ground_pins.items():
        rail_y = max_y + _RAIL_OFFSET
        _emit_rail(positions, rail_y, net_name, extra_wires, extra_flags, going_down=True)

    # Power rails: above the highest component, stacked if multiple.
    for i, (net_name, positions) in enumerate(sorted(power_pins.items())):
        rail_y = min_y - _RAIL_OFFSET - i * (LTSPICE_GRID * 4)
        _emit_rail(positions, rail_y, net_name, extra_wires, extra_flags, going_down=False)

    return extra_wires, extra_flags


def _component_y_extent(placed: list[Component]) -> tuple[int, int]:
    """Min/max y across all placed components' bboxes."""
    from wirewright.symbols.builtin import symbol_geometry

    min_y = float("inf")
    max_y = float("-inf")
    for c in placed:
        try:
            geo = symbol_geometry(c.symbol)
        except KeyError:
            continue
        assert c.y is not None
        min_y = min(min_y, c.y + geo.bbox[1])
        max_y = max(max_y, c.y + geo.bbox[3])
    if min_y == float("inf") or max_y == float("-inf"):
        return 0, 0
    return int(min_y), int(max_y)


def _emit_rail(
    pin_positions: list[tuple[int, int]],
    rail_y: int,
    net_name: str,
    wires: list[Wire],
    flags: list[Flag],
    going_down: bool,
) -> None:
    """Draw stubs from each pin to the rail Y, plus the rail itself + one FLAG."""
    if not pin_positions:
        return

    # Stub wire from each pin perpendicular to the rail.
    for px, py in pin_positions:
        if py == rail_y:
            continue
        wires.append(Wire(px, py, px, rail_y))

    # Horizontal rail spanning the leftmost to rightmost pin.
    xs = sorted({p[0] for p in pin_positions})
    if len(xs) >= 2:
        wires.append(Wire(xs[0], rail_y, xs[-1], rail_y))

    # Single FLAG per rail at the canonical end. Ground at canvas bottom uses
    # the LTspice GND symbol (FLAG net="0"); power rails use IO labels.
    flag_x = xs[-1] if going_down else xs[0]
    if going_down:
        # Ground: bring stub one extra unit below the rail so the GND symbol
        # sits below the rail, matching LTspice convention.
        terminus = rail_y + LTSPICE_GRID * 2
        wires.append(Wire(flag_x, rail_y, flag_x, terminus))
        flags.append(Flag(flag_x, terminus, "0"))
    else:
        flags.append(Flag(flag_x, rail_y, net_name))


def remove_per_pin_rail_flags(schematic: Schematic) -> None:
    """Strip pre-existing per-pin power/ground stubs/flags from the schematic.

    Called before :func:`emit_power_ground_rails` so the rail emission has
    a clean slate.
    """
    nets_by_name = {n.name: n for n in schematic.nets}
    keep_flags: list[Flag] = []
    for fl in schematic.flags:
        net = nets_by_name.get(fl.net)
        if fl.net == "0":
            continue
        if net is not None and (net.is_power or net.is_ground):
            continue
        keep_flags.append(fl)
    schematic.flags = keep_flags
