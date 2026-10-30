"""Add wires + power/ground rails to a placed Schematic.

The MLLM places components; this module runs wirewright's existing
orthogonal router + rail logic to produce axis-aligned wires that pass
``validate_placed``. The agent calls this between each model response
and the next render, so the model always critiques a properly routed
schematic.

Lifted from the HOLA placer's post-placement wiring loop — same
``route_avoiding`` + ``emit_power_ground_rails`` combo, just extracted
so the EEschematic agent can reuse it without pulling in HOLA.
"""

from __future__ import annotations

import copy

from wirewright.ir.model import Schematic
from wirewright.routing.orthogonal import route_avoiding
from wirewright.routing.rails import RailMode, emit_power_ground_rails
from wirewright.symbols.builtin import absolute_pin_position, symbol_geometry


def wire_placed_schematic(placed: Schematic, rails: RailMode = "clustered") -> Schematic:
    """Return a copy of ``placed`` with ``.wires`` and ``.flags`` populated.

    Preconditions: every component has integer ``x``, ``y``, and
    ``orientation``. Non-placed components raise ``AssertionError``.
    """
    out = copy.deepcopy(placed)
    out.wires = []
    out.flags = []

    nets_by_name = {n.name: n for n in out.nets}

    obstacles: list[tuple[int, int, int, int]] = []
    for c in out.components:
        assert c.x is not None and c.y is not None, (
            f"wire_placed_schematic: {c.ref!r} is not placed"
        )
        geo = symbol_geometry(c.symbol)
        obstacles.append(
            (c.x + geo.bbox[0], c.y + geo.bbox[1], c.x + geo.bbox[2], c.y + geo.bbox[3])
        )

    for net in out.nets:
        if net.is_power or net.is_ground or net.name == "0":
            continue  # rails handle these
        pin_positions: list[tuple[int, int]] = []
        for c in out.components:
            for pin_name, net_name in c.pins.items():
                if net_name != net.name:
                    continue
                assert c.x is not None and c.y is not None
                pin_positions.append(
                    absolute_pin_position(
                        (c.x, c.y), c.symbol, pin_name, c.orientation
                    )
                )
        unique_pins = list(dict.fromkeys(pin_positions))
        if len(unique_pins) < 2:
            continue
        anchor = unique_pins[0]
        for target in unique_pins[1:]:
            if target == anchor:
                continue
            out.wires.extend(route_avoiding(anchor, target, obstacles))

    rail_wires, rail_flags = emit_power_ground_rails(out, mode=rails)
    out.wires.extend(rail_wires)
    out.flags.extend(rail_flags)

    out.wires = [w for w in out.wires if (w.x1, w.y1) != (w.x2, w.y2)]

    # Mark ground net if the schematic has a "0" that wasn't flagged.
    for n in out.nets:
        if n.name == "0" and not n.is_ground:
            n.is_ground = True

    del nets_by_name  # silence unused in strict mode
    return out
