"""SPICE / LTspice netlist parser.

See ``docs/specs/netlist-parser.md`` for the contract. Two-pass: a pre-pass
collects ``.MODEL`` declarations and ``.SUBCKT`` bodies (rejecting nested,
unclosed, or local-inside-subckt forms); the main pass dispatches each
element line to a per-prefix handler.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from wirewright.ir.model import Component, Net, Schematic

POWER_NET_PATTERNS = re.compile(
    r"^(vcc|vdd|vee|vss|v\+|v-|\+\d+v|-\d+v)$",
    re.IGNORECASE,
)


class ParseError(Exception):
    """Raised when a netlist line cannot be parsed."""


@dataclass
class Subckt:
    """A ``.SUBCKT`` definition; body lines are pre-tokenized for fast inlining."""

    name: str
    ports: list[str]
    body_lines: list[tuple[int, str]]


def parse_spice_file(path: str | Path) -> Schematic:
    """Parse a SPICE netlist file into IR."""
    return parse_spice_text(Path(path).read_text())


def parse_spice_text(text: str) -> Schematic:
    """Parse a SPICE netlist string into IR."""
    schematic = Schematic()
    nets_seen: dict[str, Net] = {}

    preprocessed = _preprocess(text)
    models, subckts = _collect_models_and_subckts(preprocessed)

    inside_subckt = False
    for line_no, line in preprocessed:
        lower = line.lower()
        if lower.startswith(".subckt"):
            inside_subckt = True
            schematic.directives.append(line)
            continue
        if lower.startswith(".ends"):
            inside_subckt = False
            schematic.directives.append(line)
            continue
        if inside_subckt:
            continue

        if line.startswith("."):
            schematic.directives.append(line)
            continue

        tokens = line.split()
        if not tokens:
            continue

        _dispatch_element(schematic, nets_seen, line_no, line, tokens, models, subckts)

    schematic.nets = list(nets_seen.values())
    return schematic


# ----------------------------------------------------------------------------
# Pre-pass: collect .MODEL types and .SUBCKT bodies; reject malformed structure.
# ----------------------------------------------------------------------------


def _collect_models_and_subckts(
    preprocessed: list[tuple[int, str]],
) -> tuple[dict[str, str], dict[str, Subckt]]:
    models: dict[str, str] = {}
    subckts: dict[str, Subckt] = {}
    current: Subckt | None = None

    for line_no, line in preprocessed:
        lower = line.lower()

        if lower.startswith(".model"):
            tokens = line.split()
            if len(tokens) < 3:
                raise ParseError(f"line {line_no}: malformed .MODEL: {line!r}")
            if current is not None:
                raise ParseError(
                    f"line {line_no}: local .MODEL inside .SUBCKT not supported "
                    f"in v0.1; declare {tokens[1]!r} at top level"
                )
            name = tokens[1]
            type_tag = tokens[2].split("(", 1)[0].upper()
            models[name] = type_tag

        elif lower.startswith(".subckt"):
            if current is not None:
                raise ParseError(
                    f"line {line_no}: nested .SUBCKT not allowed "
                    f"(currently inside {current.name!r})"
                )
            tokens = line.split()
            if len(tokens) < 2:
                raise ParseError(f"line {line_no}: malformed .SUBCKT: {line!r}")
            current = Subckt(name=tokens[1], ports=tokens[2:], body_lines=[])
            subckts[current.name] = current

        elif lower.startswith(".ends"):
            if current is None:
                raise ParseError(f"line {line_no}: .ENDS without matching .SUBCKT")
            current = None

        elif current is not None and not line.startswith("."):
            current.body_lines.append((line_no, line))

    if current is not None:
        raise ParseError(f".SUBCKT {current.name!r} not closed by .ENDS before end of file")

    return models, subckts


# ----------------------------------------------------------------------------
# Main pass: dispatch element lines to per-prefix handlers.
# ----------------------------------------------------------------------------


def _dispatch_element(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
    models: dict[str, str],
    subckts: dict[str, Subckt],
    prefix_override: str | None = None,
) -> None:
    """Parse one element line. All handlers accept (models, subckts); unused ignored.

    ``prefix_override`` lets a caller (e.g. subckt flattening) dispatch by the
    original element prefix when the namespaced ref's first char no longer
    reflects the SPICE element type.
    """
    ref = tokens[0]
    prefix = prefix_override if prefix_override is not None else ref[0].upper()

    if prefix in ("R", "C", "L"):
        _handle_passive(schematic, nets_seen, line_no, line, tokens, prefix)
    elif prefix == "V":
        _handle_voltage(schematic, nets_seen, line_no, line, tokens)
    elif prefix == "D":
        _handle_diode(schematic, nets_seen, line_no, line, tokens)
    elif prefix == "B":
        _handle_behavioral(schematic, nets_seen, line_no, line, tokens)
    elif prefix == "E":
        _handle_vcvs(schematic, nets_seen, line_no, line, tokens)
    elif prefix == "Q":
        _handle_bjt(schematic, nets_seen, line_no, line, tokens, models)
    elif prefix == "M":
        _handle_mosfet(schematic, nets_seen, line_no, line, tokens, models)
    elif prefix == "I":
        _handle_current(schematic, nets_seen, line_no, line, tokens)
    elif prefix == "S":
        _handle_vcswitch(schematic, nets_seen, line_no, line, tokens, models)
    elif prefix == "X":
        _handle_subckt_instance(schematic, nets_seen, line_no, line, tokens, models, subckts)
    else:
        raise ParseError(
            f"line {line_no}: element {prefix!r} not yet supported "
            f"(see docs/specs/netlist-parser.md). Line: {line!r}"
        )


# ----------------------------------------------------------------------------
# Per-element handlers.
# ----------------------------------------------------------------------------


def _handle_passive(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
    prefix: str,
) -> None:
    _expect_at_least(tokens, 4, line_no, line, "<ref> <n1> <n2> <value>")
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


def _handle_voltage(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
) -> None:
    _expect_at_least(tokens, 4, line_no, line, "<ref> <n+> <n-> <value>")
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


def _handle_current(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
) -> None:
    _expect_at_least(tokens, 4, line_no, line, "<ref> <n+> <n-> <value>")
    ref, np, nn = tokens[0], tokens[1], tokens[2]
    value = " ".join(tokens[3:])
    schematic.components.append(
        Component(
            ref=ref,
            symbol="current",
            value=value,
            pins={"+": np, "-": nn},
            spice_prefix="I",
        )
    )
    for n in (np, nn):
        _record_net(nets_seen, n)


def _handle_diode(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
) -> None:
    _expect_at_least(tokens, 4, line_no, line, "<ref> <n+> <n-> <model>")
    ref, na, nk, model = tokens[0], tokens[1], tokens[2], tokens[3]
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


def _handle_behavioral(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
) -> None:
    _expect_at_least(tokens, 4, line_no, line, "<ref> <n+> <n-> V=<expr>")
    ref, np, nn = tokens[0], tokens[1], tokens[2]
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


def _handle_vcvs(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
) -> None:
    _expect_at_least(tokens, 6, line_no, line, "<ref> <n+> <n-> <nc+> <nc-> <gain>")
    ref = tokens[0]
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


def _handle_bjt(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
    models: dict[str, str],
) -> None:
    if len(tokens) == 6:
        raise ParseError(
            f"line {line_no}: 4-node Q form with substrate not supported in v0.1; "
            f"use 3-node 'Q<ref> nc nb ne <model>': {line!r}"
        )
    if len(tokens) != 5:
        raise ParseError(f"line {line_no}: expected 'Q<ref> nc nb ne <model>': {line!r}")
    ref, nc, nb, ne, model_name = tokens
    model_type = models.get(model_name)
    if model_type is None:
        raise ParseError(
            f"line {line_no}: unknown BJT model {model_name!r}; "
            f"declare with '.model {model_name} NPN(...)' or PNP(...)"
        )
    if model_type == "NPN":
        symbol = "npn"
    elif model_type == "PNP":
        symbol = "pnp"
    else:
        raise ParseError(
            f"line {line_no}: BJT model {model_name!r} has unsupported type "
            f"{model_type!r} (expected NPN or PNP)"
        )
    schematic.components.append(
        Component(
            ref=ref,
            symbol=symbol,
            pins={"C": nc, "B": nb, "E": ne},
            spice_prefix="Q",
            spice_model=model_name,
        )
    )
    for n in (nc, nb, ne):
        _record_net(nets_seen, n)


def _handle_mosfet(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
    models: dict[str, str],
) -> None:
    if len(tokens) not in (5, 6):
        raise ParseError(f"line {line_no}: expected 'M<ref> nd ng ns [nb] <model>': {line!r}")
    ref = tokens[0]
    model_name = tokens[-1]
    nodes = tokens[1:-1]
    model_type = models.get(model_name)
    if model_type not in ("NMOS", "PMOS"):
        raise ParseError(
            f"line {line_no}: unknown MOSFET model {model_name!r} "
            f"(declare with '.model {model_name} NMOS(...)' or PMOS(...))"
        )
    if len(nodes) == 4:
        nd, ng, ns, nb = nodes
        symbol = "nmos4" if model_type == "NMOS" else "pmos4"
        pins: dict[str, str] = {"D": nd, "G": ng, "S": ns, "B": nb}
    else:
        nd, ng, ns = nodes
        symbol = "nmos" if model_type == "NMOS" else "pmos"
        pins = {"D": nd, "G": ng, "S": ns}
    schematic.components.append(
        Component(
            ref=ref,
            symbol=symbol,
            pins=pins,
            spice_prefix="M",
            spice_model=model_name,
        )
    )
    for n in nodes:
        _record_net(nets_seen, n)


def _handle_vcswitch(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
    models: dict[str, str],
) -> None:
    _expect_at_least(tokens, 6, line_no, line, "<ref> <n+> <n-> <nc+> <nc-> <model>")
    ref = tokens[0]
    np, nn, ncp, ncn, model_name = tokens[1], tokens[2], tokens[3], tokens[4], tokens[5]
    model_type = models.get(model_name)
    if model_type != "SW":
        raise ParseError(
            f"line {line_no}: unknown switch model {model_name!r} "
            f"(declare with '.model {model_name} SW(...)')"
        )
    schematic.components.append(
        Component(
            ref=ref,
            symbol="sw",
            pins={"A": np, "B": nn, "NC+": ncp, "NC-": ncn},
            spice_prefix="S",
            spice_model=model_name,
        )
    )
    for n in (np, nn, ncp, ncn):
        _record_net(nets_seen, n)


def _handle_subckt_instance(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
    models: dict[str, str],
    subckts: dict[str, Subckt],
    _expansion_stack: tuple[str, ...] = (),
) -> None:
    """Flatten X<ref> ... <subckt_name> by inlining the subckt body.

    Namespace prefix: ``ref[1:] + "."`` per docs/specs/netlist-parser.md
    (drops the leading ``X``).
    """
    if len(tokens) < 3:
        raise ParseError(f"line {line_no}: malformed X card: {line!r}")
    ref = tokens[0]
    subckt_name = tokens[-1]
    call_site_nets = tokens[1:-1]

    if subckt_name in _expansion_stack:
        raise ParseError(
            f"line {line_no}: subcircuit recursion detected: "
            f"{' → '.join((*_expansion_stack, subckt_name))}"
        )
    sub = subckts.get(subckt_name)
    if sub is None:
        raise ParseError(f"line {line_no}: unknown subcircuit {subckt_name!r}")
    if len(call_site_nets) != len(sub.ports):
        raise ParseError(
            f"line {line_no}: subcircuit {subckt_name!r} expects {len(sub.ports)} "
            f"ports {sub.ports!r}, got {len(call_site_nets)}: {call_site_nets!r}"
        )

    port_map = dict(zip(sub.ports, call_site_nets, strict=True))
    namespace = ref[1:] + "." if ref[:1].upper() == "X" else ref + "."
    new_stack = (*_expansion_stack, subckt_name)

    def remap_net(net: str) -> str:
        if net in port_map:
            return port_map[net]
        if net == "0" or net.lower() == "gnd":
            return "0"
        return namespace + net

    for body_line_no, body_line in sub.body_lines:
        body_tokens = body_line.split()
        body_prefix_char = body_tokens[0][0].upper()

        if body_prefix_char == "X":
            renamed_x_tokens = (
                [namespace + body_tokens[0]]
                + [remap_net(n) for n in body_tokens[1:-1]]
                + [body_tokens[-1]]
            )
            _handle_subckt_instance(
                schematic,
                nets_seen,
                body_line_no,
                " ".join(renamed_x_tokens),
                renamed_x_tokens,
                models,
                subckts,
                new_stack,
            )
            continue

        renamed_tokens = [namespace + body_tokens[0]]
        arity = _node_arity(body_prefix_char, body_tokens, body_line_no)
        renamed_tokens.extend(remap_net(n) for n in body_tokens[1 : 1 + arity])
        renamed_tokens.extend(body_tokens[1 + arity :])
        _dispatch_element(
            schematic,
            nets_seen,
            body_line_no,
            " ".join(renamed_tokens),
            renamed_tokens,
            models,
            subckts,
            prefix_override=body_prefix_char,
        )


def _node_arity(prefix: str, tokens: list[str], line_no: int) -> int:
    """Net-token count for an element line (excluding ref and value/model)."""
    if prefix in ("R", "C", "L", "V", "I", "D", "B"):
        return 2
    if prefix == "Q":
        return 3
    if prefix in ("E", "S", "G", "F", "H"):
        return 4
    if prefix == "M":
        return len(tokens) - 2
    raise ParseError(f"line {line_no}: unknown element prefix {prefix!r} inside subcircuit body")


# ----------------------------------------------------------------------------
# Line preprocessor: '+' continuation joining + comment skipping.
# ----------------------------------------------------------------------------


def _preprocess(text: str) -> list[tuple[int, str]]:
    """Return ``(first_line_no, joined_line)`` tuples after applying SPICE rules."""
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
