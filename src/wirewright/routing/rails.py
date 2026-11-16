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
from wirewright.routing.orthogonal import route_avoiding
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

    # Pre-compute every rail flag's (x, y, net) so each rail emission
    # can treat OTHER rails' flags as point obstacles. Without this,
    # VSS's upward stub at x=X passes through VDD's rail-flag position
    # at (X, vdd_rail_y), silently shorting VSS to VDD. Seen on HOLA's
    # 4 broken tb303 fixtures and the 2026-11-16 EEschematic run.
    planned_flags = _plan_rail_flags(
        ground_pins, power_pins, min_y, max_y, cluster_gap, mode
    )
    # Same for component pins on other nets — a rail stub passing
    # through a non-rail-net pin shorts just as badly.
    pins_by_net = _all_pin_positions_by_net(placed)

    def obstacles_for(current_net: str) -> list[tuple[int, int]]:
        obs: list[tuple[int, int]] = []
        for other_net, positions in pins_by_net.items():
            if other_net != current_net:
                obs.extend(positions)
        for fx, fy, fnn in planned_flags:
            if fnn != current_net:
                obs.append((fx, fy))
        return obs

    if mode == "clustered":
        for net_name, positions in ground_pins.items():
            rail_y = max_y + _RAIL_OFFSET
            for cluster in _cluster_by_x(positions, cluster_gap):
                _emit_cluster(
                    cluster, rail_y, net_name, extra_wires, extra_flags,
                    going_down=True, pin_obstacles=obstacles_for(net_name),
                )
        for i, (net_name, positions) in enumerate(sorted(power_pins.items())):
            rail_y = min_y - _RAIL_OFFSET - i * (LTSPICE_GRID * 4)
            for cluster in _cluster_by_x(positions, cluster_gap):
                _emit_cluster(
                    cluster, rail_y, net_name, extra_wires, extra_flags,
                    going_down=False, pin_obstacles=obstacles_for(net_name),
                )
        return extra_wires, extra_flags

    # mode == "global": one rail per net, spanning everything.
    for net_name, positions in ground_pins.items():
        rail_y = max_y + _RAIL_OFFSET
        _emit_rail(
            positions, rail_y, net_name, extra_wires, extra_flags,
            going_down=True, pin_obstacles=obstacles_for(net_name),
        )
    for i, (net_name, positions) in enumerate(sorted(power_pins.items())):
        rail_y = min_y - _RAIL_OFFSET - i * (LTSPICE_GRID * 4)
        _emit_rail(
            positions, rail_y, net_name, extra_wires, extra_flags,
            going_down=False, pin_obstacles=obstacles_for(net_name),
        )

    return extra_wires, extra_flags


def _plan_rail_flags(
    ground_pins: dict[str, list[tuple[int, int]]],
    power_pins: dict[str, list[tuple[int, int]]],
    min_y: int,
    max_y: int,
    cluster_gap: int,
    mode: RailMode,
) -> list[tuple[int, int, str]]:
    """Compute (x, y, net) for every flag ``emit_power_ground_rails`` will drop.

    Mirrors the geometry calculations in the main emit function so each
    rail knows where every other rail's terminus will sit. ``scattered``
    mode returns empty — stubs don't exist there, so no collisions.
    """
    if mode == "scattered":
        return []
    out: list[tuple[int, int, str]] = []
    for net_name, positions in ground_pins.items():
        rail_y = max_y + _RAIL_OFFSET
        terminus = rail_y + LTSPICE_GRID * 2
        clusters = _cluster_by_x(positions, cluster_gap) if mode == "clustered" else [positions]
        for cluster in clusters:
            xs = sorted({p[0] for p in cluster})
            flag_x = xs[-1]  # going_down end
            out.append((flag_x, terminus, net_name))
    for i, (net_name, positions) in enumerate(sorted(power_pins.items())):
        rail_y = min_y - _RAIL_OFFSET - i * (LTSPICE_GRID * 4)
        clusters = _cluster_by_x(positions, cluster_gap) if mode == "clustered" else [positions]
        for cluster in clusters:
            xs = sorted({p[0] for p in cluster})
            flag_x = xs[0]  # going_up end
            out.append((flag_x, rail_y, net_name))
    return out


def _all_pin_positions_by_net(
    placed: list[Component],
) -> dict[str, list[tuple[int, int]]]:
    """Component pin absolute positions grouped by net name."""
    out: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for c in placed:
        assert c.x is not None and c.y is not None
        for pin_name, net_name in c.pins.items():
            out[net_name].append(
                absolute_pin_position((c.x, c.y), c.symbol, pin_name, c.orientation)
            )
    return out


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
    pin_obstacles: list[tuple[int, int]] | None = None,
) -> None:
    """Draw stubs from each pin to the rail Y, plus the rail itself + one FLAG.

    When ``pin_obstacles`` is non-empty, stubs route via
    :func:`route_avoiding` so a straight vertical that would cross an
    other-net pin or an other-rail flag turns into an L-bend. Empty
    obstacle list preserves the pre-fix straight-stub shape.
    """
    if not pin_positions:
        return
    pin_obstacles = pin_obstacles or []

    # Stub wire from each pin to the rail, avoiding other-net pins
    # and other-rail flag positions.
    for px, py in pin_positions:
        if py == rail_y:
            continue
        wires.extend(
            route_avoiding((px, py), (px, rail_y), [], pin_obstacles=pin_obstacles)
        )

    # Horizontal rail spanning the leftmost to rightmost pin. Also
    # routed with obstacles so a long rail wire can't pass through a
    # cross-net pin on the same y row.
    xs = sorted({p[0] for p in pin_positions})
    if len(xs) >= 2:
        wires.extend(
            route_avoiding(
                (xs[0], rail_y), (xs[-1], rail_y), [],
                pin_obstacles=pin_obstacles,
            )
        )

    # Single FLAG per rail at the canonical end. Ground at canvas bottom uses
    # the LTspice GND symbol (FLAG net="0"); power rails use IO labels.
    flag_x = xs[-1] if going_down else xs[0]
    if going_down:
        # Ground: bring stub one extra unit below the rail so the GND symbol
        # sits below the rail, matching LTspice convention.
        terminus = rail_y + LTSPICE_GRID * 2
        wires.extend(
            route_avoiding(
                (flag_x, rail_y), (flag_x, terminus), [],
                pin_obstacles=pin_obstacles,
            )
        )
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
    pin_obstacles: list[tuple[int, int]] | None = None,
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
    _emit_rail(
        cluster, rail_y, net_name, wires, flags,
        going_down=going_down, pin_obstacles=pin_obstacles,
    )


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
