"""Regression tests for emit_power_ground_rails column collision.

When VDD and VSS pins sit on the same x column, the straight-vertical
stub from VSS pin up to the VSS rail (further out than VDD's) passes
through the VDD rail flag's position — electrically shorting VSS to
VDD. Same pattern caught by the wire-connectivity oracle on 4 of 21
HOLA fixtures (tb303-envelope, -saw-cliptop, -cliptop-bottom,
-vco-integrated).

See ``docs/notes/eeschematic-verdict.md`` for the full discovery trail.
"""

from __future__ import annotations

from wirewright.ir.model import Component, Net, Schematic
from wirewright.ir.validate import check_wires_induce_exact_nets
from wirewright.routing.rails import emit_power_ground_rails


def _vdd_vss_same_column() -> Schematic:
    """Minimal repro: two voltage sources at the same x column.

    VDD source at (0, 0), VSS source at (0, 128). Both contribute a
    ``+`` pin (power net) and a ``-`` pin (ground). Rails stack
    vertically above / below; VDD and VSS are two distinct power rails
    that both end up at x=0 because both sources are at x=0.
    """
    vdd = Component(
        ref="VDD",
        symbol="voltage",
        value="DC 12",
        pins={"+": "VDD", "-": "0"},
        x=0,
        y=0,
        orientation="R0",
    )
    vss = Component(
        ref="VSS",
        symbol="voltage",
        value="DC -12",
        pins={"+": "VSS", "-": "0"},
        x=0,
        y=128,
        orientation="R0",
    )
    return Schematic(
        components=[vdd, vss],
        nets=[
            Net("VDD", is_power=True),
            Net("VSS", is_power=True),
            Net("0", is_ground=True),
        ],
    )


def test_rails_do_not_short_when_vdd_vss_share_column() -> None:
    """Emit rails on the collision layout; strict oracle must pass."""
    s = _vdd_vss_same_column()
    wires, flags = emit_power_ground_rails(s, mode="clustered")
    s.wires = wires
    s.flags = flags
    # The oracle is the referee. A straight-vertical stub for VSS
    # through (0, VDD_rail_y) would short — a correct routing (L-bend
    # around, or offset column) makes this pass.
    check_wires_induce_exact_nets(s, strict=True)


def test_rails_also_work_in_global_mode() -> None:
    """Same collision pattern, mode='global' — must also route around."""
    s = _vdd_vss_same_column()
    wires, flags = emit_power_ground_rails(s, mode="global")
    s.wires = wires
    s.flags = flags
    check_wires_induce_exact_nets(s, strict=True)
