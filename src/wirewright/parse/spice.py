"""SPICE / LTspice netlist parser.

See ``docs/specs/netlist-parser.md`` for the contract. Supports the
two-terminal passives (R/C/L), diodes (D), independent sources (V/I),
behavioral sources (B = bv/bi), and four-terminal voltage-controlled voltage
sources (E). Subcircuits, BJTs, MOSFETs, and the remaining controlled-source
prefixes (F/G/H) land in later phases.
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
    """Parse a SPICE netlist string into IR."""
    schematic = Schematic()
    nets_seen: dict[str, Net] = {}

    for line_no, line in _preprocess(text):
        if line.startswith("."):
            schematic.directives.append(line)
            continue

        tokens = line.split()
        if not tokens:
            continue

        ref = tokens[0]
        prefix = ref[0].upper()

        if prefix in ("R", "C", "L"):
            _expect_at_least(tokens, 4, line_no, line, "<ref> <n1> <n2> <value>")
            n1, n2, value = tokens[1], tokens[2], tokens[3]
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
            _expect_at_least(tokens, 4, line_no, line, "<ref> <n+> <n-> <value>")
            np, nn = tokens[1], tokens[2]
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

        elif prefix == "D":
            _expect_at_least(tokens, 4, line_no, line, "<ref> <n+> <n-> <model>")
            na, nk, model = tokens[1], tokens[2], tokens[3]
            schematic.components.append(
                Component(
                    ref=ref,
                    symbol="diode",
                    pins={"A": na, "K": nk},
                    spice_prefix="D",
                    spice_model=model,
                )
            )
            for n in (na, nk):
                _record_net(nets_seen, n)

        elif prefix == "B":
            _expect_at_least(tokens, 4, line_no, line, "<ref> <n+> <n-> V=<expr>")
            np, nn = tokens[1], tokens[2]
            value = " ".join(tokens[3:])
            symbol = "bi" if value[:2].upper() == "I=" else "bv"
            schematic.components.append(
                Component(
                    ref=ref,
                    symbol=symbol,
                    value=value,
                    pins={"+": np, "-": nn},
                    spice_prefix="B",
                )
            )
            for n in (np, nn):
                _record_net(nets_seen, n)

        elif prefix == "E":
            _expect_at_least(tokens, 6, line_no, line, "<ref> <n+> <n-> <nc+> <nc-> <gain>")
            np, nn, ncp, ncn = tokens[1], tokens[2], tokens[3], tokens[4]
            value = " ".join(tokens[5:])
            schematic.components.append(
                Component(
                    ref=ref,
                    symbol="e",
                    value=value,
                    pins={"+": np, "-": nn, "P": ncp, "N": ncn},
                    spice_prefix="E",
                )
            )
            for n in (np, nn, ncp, ncn):
                _record_net(nets_seen, n)

        else:
            raise ParseError(
                f"line {line_no}: element '{prefix}' not yet supported "
                f"(see docs/specs/netlist-parser.md). Line: {line!r}"
            )

    schematic.nets = list(nets_seen.values())
    return schematic


def _preprocess(text: str) -> list[tuple[int, str]]:
    """Return ``(first_line_no, joined_line)`` tuples after applying SPICE rules.

    - Comment lines (``*``) are dropped without affecting continuation chains.
    - Blank lines break continuation chains.
    - Lines starting with ``+`` are appended (separated by a single space) to
      the prior logical line; an orphan ``+`` raises :class:`ParseError`.
    """
    out: list[tuple[int, str]] = []
    can_continue = False
    for raw_no, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            can_continue = False
            continue
        if stripped.startswith("*"):
            continue
        if stripped.startswith("+"):
            if not can_continue:
                raise ParseError(f"line {raw_no}: orphan '+' continuation")
            prior_no, prior = out[-1]
            out[-1] = (prior_no, prior + " " + stripped[1:].strip())
            continue
        out.append((raw_no, stripped))
        can_continue = True
    return out


def _expect_at_least(
    tokens: list[str], required: int, line_no: int, line: str, expected: str
) -> None:
    if len(tokens) < required:
        raise ParseError(f"line {line_no}: expected '{expected}': {line!r}")


def _record_net(seen: dict[str, Net], name: str) -> None:
    if name in seen:
        return
    is_ground = name == "0" or name.lower() == "gnd"
    is_power = bool(POWER_NET_PATTERNS.match(name)) and not is_ground
    canonical = "0" if is_ground else name
    seen[canonical] = Net(name=canonical, is_power=is_power, is_ground=is_ground)
