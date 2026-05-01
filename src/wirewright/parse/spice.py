"""SPICE / LTspice netlist parser.

PHASE 2. Currently a minimal stub that handles the simplest possible cases
(R, C, V elements, no subcircuits) so that the demo and basic tests work.
The full implementation lands in Phase 2.

See docs/specs/netlist-parser.md for the contract.
"""

from __future__ import annotations

import re
from pathlib import Path

from wirewright.ir.model import Component, Net, Schematic

POWER_NET_PATTERNS = re.compile(
    r"^(vcc|vdd|vee|vss|v\+|v-|\+\d+v|-\d+v)$",
    re.IGNORECASE,
)


class ParseError(Exception):
    """Raised when a netlist line cannot be parsed."""


def parse_spice_file(path: str | Path) -> Schematic:
    """Parse a SPICE netlist file into IR."""
    text = Path(path).read_text()
    return parse_spice_text(text)


def parse_spice_text(text: str) -> Schematic:
    """Parse a SPICE netlist string into IR.

    PHASE 0 implementation: handles R, C, V on simple two-terminal cards only.
    Anything more complex raises ParseError so that Phase 2 can replace this
    cleanly.
    """
    schematic = Schematic()
    nets_seen: dict[str, Net] = {}

    for raw_line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("*"):
            continue
        if line.startswith("."):
            schematic.directives.append(line)
            continue

        tokens = line.split()
        if not tokens:
            continue

        elem = tokens[0]
        prefix = elem[0].upper()

        if prefix in ("R", "C", "L"):
            # FORMAT: <ref> <node1> <node2> <value> [more...]
            if len(tokens) < 4:
                raise ParseError(
                    f"line {raw_line_no}: expected '<ref> <n1> <n2> <value>': {line!r}"
                )
            ref, n1, n2, value = tokens[0], tokens[1], tokens[2], tokens[3]
            symbol = {"R": "res", "C": "cap", "L": "ind"}[prefix]
            schematic.components.append(
                Component(
                    ref=ref,
                    symbol=symbol,
                    value=value,
                    pins={"1": n1, "2": n2},
                    spice_prefix=prefix,
                )
            )
            for n in (n1, n2):
                _record_net(nets_seen, n)
        elif prefix == "V":
            if len(tokens) < 4:
                raise ParseError(
                    f"line {raw_line_no}: expected '<ref> <n+> <n-> <value>': {line!r}"
                )
            ref, np, nn = tokens[0], tokens[1], tokens[2]
            value = " ".join(tokens[3:])
            schematic.components.append(
                Component(
                    ref=ref,
                    symbol="voltage",
                    value=value,
                    pins={"+": np, "-": nn},
                    spice_prefix="V",
                )
            )
            for n in (np, nn):
                _record_net(nets_seen, n)
        else:
            raise ParseError(
                f"line {raw_line_no}: element '{prefix}' not supported in v0.0.1 "
                f"(see docs/PLAN.md, Phase 2). Line: {line!r}"
            )

    schematic.nets = list(nets_seen.values())
    return schematic


def _record_net(seen: dict[str, Net], name: str) -> None:
    if name in seen:
        return
    is_ground = name == "0" or name.lower() == "gnd"
    is_power = bool(POWER_NET_PATTERNS.match(name)) and not is_ground
    canonical = "0" if is_ground else name
    seen[canonical] = Net(name=canonical, is_power=is_power, is_ground=is_ground)
