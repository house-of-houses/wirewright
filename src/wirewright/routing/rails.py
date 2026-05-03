"""Power/ground rail synthesis.

After component placement, ground/power nets get rendered as one of three
visual styles selected by ``mode``:

- ``"scattered"`` — one FLAG per pin, no rail wires (LTspice default).
  Good when pins are spread thin across the canvas.
- ``"clustered"`` (default) — pins are 1-D clustered by x-proximity.
  Each cluster of size ≥2 gets its own short horizontal rail segment with
  one FLAG; singleton clusters drop a FLAG at the pin position with no
  stub. Best general-purpose choice.
- ``"global"`` — every pin on the same net is wired to one cross-canvas
  rail (top for power, bottom for ground). Visually clean on tightly
  packed schematics; noisy on sparse ones.

Per :doc:`docs/specs/placer-interface.md` "Power and ground handling":
every placer back end emits these via this helper.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from wirewright.ir.model import Component, Flag, Schematic, Wire
from wirewright.ir.validate import LTSPICE_GRID
from wirewright.symbols.builtin import absolute_pin_position

RailMode = Literal["scattered", "clustered", "global"]

_RAIL_OFFSET = LTSPICE_GRID * 4
"""Distance from the canvas extremum to the rail itself."""

_DEFAULT_CLUSTER_GAP = LTSPICE_GRID * 6
"""x-distance threshold for joining adjacent pins in clustered mode (~one
component-width-and-a-half). Pins closer than this group together; pins
farther apart become separate rail segments."""


def _cluster_by_x(
    positions: list[tuple[int, int]], gap_threshold: int
) -> list[list[tuple[int, int]]]:
    """Group pin positions into x-adjacent clusters.

    Sorts by x, then splits whenever the gap to the previous pin exceeds
    ``gap_threshold``. Singletons stay as length-1 clusters.
    """
    if not positions:
        return []
    sorted_pins = sorted(positions, key=lambda p: p[0])
    clusters: list[list[tuple[int, int]]] = [[sorted_pins[0]]]
    for p in sorted_pins[1:]:
        if p[0] - clusters[-1][-1][0] <= gap_threshold:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return clusters


def emit_power_ground_rails(
    schematic: Schematic,
    mode: RailMode = "clustered",
    cluster_gap: int = _DEFAULT_CLUSTER_GAP,
) -> tuple[list[Wire], list[Flag]]:
    """Compute rail wires + FLAGs for every power/ground net.

    Returns ``(extra_wires, extra_flags)``. Caller appends them to the
    schematic. Skips silently when the schematic has no placed components,
    no nets, or no power/ground membership. ``mode`` selects the visual
    style — see module docstring for tradeoffs.
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

    extra_wires: list[Wire] = []
    extra_flags: list[Flag] = []

    if mode == "scattered":
        for net_name, positions in ground_pins.items():
            for px, py in positions:
                extra_flags.append(Flag(px, py, net_name))
        for net_name, positions in power_pins.items():
            for px, py in positions:
                extra_flags.append(Flag(px, py, net_name))
        return extra_wires, extra_flags

    # Both clustered and global modes need rail bands.
    min_y, max_y = _component_y_extent(placed)

    if mode == "clustered":
        for net_name, positions in ground_pins.items():
            rail_y = max_y + _RAIL_OFFSET
            for cluster in _cluster_by_x(positions, cluster_gap):
                _emit_cluster(cluster, rail_y, net_name, extra_wires, extra_flags, going_down=True)
        for i, (net_name, positions) in enumerate(sorted(power_pins.items())):
            rail_y = min_y - _RAIL_OFFSET - i * (LTSPICE_GRID * 4)
            for cluster in _cluster_by_x(positions, cluster_gap):
                _emit_cluster(cluster, rail_y, net_name, extra_wires, extra_flags, going_down=False)
        return extra_wires, extra_flags

    # mode == "global": one rail per net, spanning everything.
    for net_name, positions in ground_pins.items():
        rail_y = max_y + _RAIL_OFFSET
        _emit_rail(positions, rail_y, net_name, extra_wires, extra_flags, going_down=True)
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


def _emit_cluster(
    cluster: list[tuple[int, int]],
    rail_y: int,
    net_name: str,
    wires: list[Wire],
    flags: list[Flag],
    going_down: bool,
) -> None:
    """Emit one local rail per cluster.

    Multi-pin clusters get the same shape as a global rail (stubs + a
    horizontal segment + one FLAG) but spanning only this cluster's x
    extent. Singletons get the stub-and-FLAG without the horizontal
    segment, so the FLAG lands in the same rail band as its neighbors
    rather than overlapping the component body.
    """
    if not cluster:
        return
    _emit_rail(cluster, rail_y, net_name, wires, flags, going_down=going_down)


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
