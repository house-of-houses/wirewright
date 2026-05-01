"""Naive grid placer: arrange components in a regular grid in input order.

This is intentionally trivial. Its job is to prove the IR → placer → emitter
pipeline works end-to-end and to serve as a fallback when HOLA can't lay
out a particular graph (the 3 known abort fixtures).

Quality of layout: bad. Use ``hola`` for real circuits.
"""

from __future__ import annotations

import copy
import math
from collections import defaultdict
from typing import Any

from wirewright.ir.model import Component, Flag, Schematic, Wire
from wirewright.ir.validate import LTSPICE_GRID, validate, validate_placed
from wirewright.placers.base import Placer
from wirewright.routing.orthogonal import l_shape
from wirewright.symbols import absolute_pin_position, symbol_geometry

# Grid spacing for the naive placer. 16 = LTspice grid; 8 grid cells = 128 IR units.
CELL_W = 16 * 12
CELL_H = 16 * 10
MARGIN = 16 * 4


class NaivePlacer(Placer):
    """Drop every component into a grid cell, no overlap, simple wire stubs."""

    name = "naive"

    def place(
        self,
        schematic: Schematic,
        hints: dict[str, Any] | None = None,
    ) -> Schematic:
        validate(schematic)
        out = copy.deepcopy(schematic)

        pinned: dict[str, tuple[int, int, str]] = (hints or {}).get("pinned") or {}

        # Pinned components first; remaining fill a square-ish grid around them.
        unpinned = [c for c in out.components if c.ref not in pinned]
        n = len(unpinned)
        cols = max(1, math.ceil(math.sqrt(n)))
        # Reserve x=0..pinned_xmax for pinned components; grid starts to the right.
        pinned_x_max = max((px for px, _, _ in pinned.values()), default=-CELL_W)
        grid_origin_x = MARGIN + pinned_x_max + CELL_W

        for c in out.components:
            if c.ref in pinned:
                px, py, orient = pinned[c.ref]
                c.x, c.y = px, py
                c.orientation = orient  # type: ignore[assignment]
        for i, comp in enumerate(unpinned):
            row, col = divmod(i, cols)
            comp.x = grid_origin_x + col * CELL_W
            comp.y = MARGIN + row * CELL_H
            comp.orientation = "R0"

        # Group component pins by the net they belong to.
        net_pins: dict[str, list[tuple[Component, str]]] = defaultdict(list)
        for comp in out.components:
            for pin_name, net_name in comp.pins.items():
                net_pins[net_name].append((comp, pin_name))

        # Emit wires and flags.
        out.wires = []
        out.flags = []

        for net in out.nets:
            pins = net_pins.get(net.name, [])
            if not pins:
                continue

            if net.is_ground or net.name == "0":
                # Drop a GND flag at every pin connected to ground.
                for comp, pin_name in pins:
                    px, py = absolute_pin_position(
                        (comp.x or 0, comp.y or 0),
                        comp.symbol,
                        pin_name,
                        comp.orientation,
                    )
                    # Stub wire down from the pin to a clear point, then GND flag.
                    stub_y = py + LTSPICE_GRID * 2
                    out.wires.append(Wire(px, py, px, stub_y))
                    out.flags.append(Flag(px, stub_y, "0"))
                continue

            if net.is_power:
                # Label power nets at every pin connection.
                for comp, pin_name in pins:
                    px, py = absolute_pin_position(
                        (comp.x or 0, comp.y or 0),
                        comp.symbol,
                        pin_name,
                        comp.orientation,
                    )
                    out.flags.append(Flag(px, py, net.name))
                continue

            # Ordinary signal net: connect pairwise pins with L-shaped wires.
            # This is the visually-bad "spaghetti" the real placers replace.
            positions = [
                absolute_pin_position((c.x or 0, c.y or 0), c.symbol, p, c.orientation)
                for c, p in pins
            ]
            anchor = positions[0]
            for px, py in positions[1:]:
                out.wires.extend(l_shape(anchor, (px, py)))

            # Label nets with two or more endpoints with an IO flag at the anchor
            # so the user can see which net is which.
            if len(pins) >= 2:
                out.flags.append(Flag(anchor[0], anchor[1], net.name))

        validate_placed(out)
        return out


# Suppress unused-import warning; keeping the import documents the dependency.
_ = symbol_geometry
