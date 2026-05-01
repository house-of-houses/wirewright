"""End-to-end round-trip: synthetic IR → .asc → IR.

Pure synthetic data; no fixture dependencies.
"""

from __future__ import annotations

from wirewright.emit.asc import emit_asc
from wirewright.ir.model import Component, Flag, Net, Schematic, Wire
from wirewright.parse.ltspice_asc import parse_asc_text


def _flagged_two_resistor_schematic() -> Schematic:
    """Two resistors in series with every net flagged."""
    return Schematic(
        components=[
            Component(
                ref="R1",
                symbol="res",
                value="10k",
                pins={"1": "n1", "2": "vin"},
                spice_prefix="R",
                x=64,
                y=64,
                orientation="R0",
            ),
            Component(
                ref="R2",
                symbol="res",
                value="10k",
                pins={"1": "n1", "2": "0"},
                spice_prefix="R",
                x=256,
                y=64,
                orientation="R0",
            ),
        ],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
        wires=[
            Wire(80, 80, 80, 48),  # R1.pin1 → bend
            Wire(80, 48, 272, 48),  # bend (n1)
            Wire(272, 48, 272, 80),  # bend → R2.pin1
        ],
        flags=[
            Flag(80, 160, "vin"),  # at R1.pin2
            Flag(80, 48, "n1"),
            Flag(272, 160, "0"),  # at R2.pin2
        ],
        directives=[".tran 1m"],
    )


def _three_resistor_with_unflagged_internal_net() -> Schematic:
    """Three resistors in series with the middle nodes intentionally un-flagged.

    The parser must re-discover the un-flagged nets via union-find and assign
    synthetic names. The test asserts connectivity isomorphism, not name
    identity.
    """
    return Schematic(
        components=[
            Component(
                ref="R1",
                symbol="res",
                value="1k",
                pins={"1": "internal_a", "2": "vin"},
                spice_prefix="R",
                x=64,
                y=64,
                orientation="R0",
            ),
            Component(
                ref="R2",
                symbol="res",
                value="1k",
                pins={"1": "internal_a", "2": "internal_b"},
                spice_prefix="R",
                x=256,
                y=64,
                orientation="R0",
            ),
            Component(
                ref="R3",
                symbol="res",
                value="1k",
                pins={"1": "internal_b", "2": "0"},
                spice_prefix="R",
                x=448,
                y=64,
                orientation="R0",
            ),
        ],
        nets=[
            Net("vin"),
            Net("internal_a"),
            Net("internal_b"),
            Net("0", is_ground=True),
        ],
        wires=[
            # internal_a: R1.pin1=(80,80) ↔ R2.pin1=(272,80) via L-shape above.
            Wire(80, 80, 80, 48),
            Wire(80, 48, 272, 48),
            Wire(272, 48, 272, 80),
            # internal_b: R2.pin2=(272,160) ↔ R3.pin1=(464,80). Routed *around*
            # R3 (down → right of R3 → up → left → down) so it never crosses
            # R3.pin2=(464,160).
            Wire(272, 160, 272, 192),
            Wire(272, 192, 560, 192),
            Wire(560, 48, 560, 192),
            Wire(464, 48, 560, 48),
            Wire(464, 48, 464, 80),
        ],
        flags=[
            Flag(80, 160, "vin"),  # R1.pin2 only
            Flag(464, 160, "0"),  # R3.pin2 only
            # internal_a and internal_b deliberately un-flagged.
        ],
        directives=[],
    )


# ----------------------------- All-flagged tests -----------------------------


def test_round_trip_preserves_components() -> None:
    original = _flagged_two_resistor_schematic()
    parsed = parse_asc_text(emit_asc(original))
    refs_a = {c.ref for c in original.components}
    refs_b = {c.ref for c in parsed.components}
    assert refs_a == refs_b
    for ref in refs_a:
        a = original.component_by_ref(ref)
        b = parsed.component_by_ref(ref)
        assert (a.symbol, a.value, a.x, a.y, a.orientation) == (
            b.symbol,
            b.value,
            b.x,
            b.y,
            b.orientation,
        )


def test_round_trip_preserves_pin_connectivity() -> None:
    original = _flagged_two_resistor_schematic()
    parsed = parse_asc_text(emit_asc(original))
    for ref in {c.ref for c in original.components}:
        assert parsed.component_by_ref(ref).pins == original.component_by_ref(ref).pins


def test_round_trip_preserves_wires() -> None:
    original = _flagged_two_resistor_schematic()
    parsed = parse_asc_text(emit_asc(original))
    assert {(w.x1, w.y1, w.x2, w.y2) for w in original.wires} == {
        (w.x1, w.y1, w.x2, w.y2) for w in parsed.wires
    }


def test_round_trip_preserves_flags() -> None:
    original = _flagged_two_resistor_schematic()
    parsed = parse_asc_text(emit_asc(original))
    assert {(f.x, f.y, f.net) for f in original.flags} == {(f.x, f.y, f.net) for f in parsed.flags}


def test_round_trip_preserves_directives() -> None:
    original = _flagged_two_resistor_schematic()
    parsed = parse_asc_text(emit_asc(original))
    assert parsed.directives == original.directives


def test_round_trip_preserves_net_names() -> None:
    original = _flagged_two_resistor_schematic()
    parsed = parse_asc_text(emit_asc(original))
    assert {n.name for n in original.nets} == {n.name for n in parsed.nets}


# ------------------- Connectivity-isomorphism test ---------------------


def _connectivity_signature(s: Schematic) -> dict[str, frozenset[tuple[str, str]]]:
    """For each net, the frozenset of (component_ref, pin_name) tuples on it."""
    sig: dict[str, set[tuple[str, str]]] = {}
    for c in s.components:
        for pin_name, net_name in c.pins.items():
            sig.setdefault(net_name, set()).add((c.ref, pin_name))
    return {k: frozenset(v) for k, v in sig.items()}


def test_round_trip_with_unflagged_nets_preserves_connectivity_isomorphism() -> None:
    """Net names may be renamed by the parser; topology must still match."""
    original = _three_resistor_with_unflagged_internal_net()
    parsed = parse_asc_text(emit_asc(original))

    sig_a = _connectivity_signature(original)
    sig_b = _connectivity_signature(parsed)

    # Same multiset of net signatures (frozensets of (ref, pin) tuples)
    # implies a bijection exists by construction. Sort by canonicalized
    # tuple-of-tuples since frozenset's `<` is subset, not lex order.
    multiset_a = sorted(tuple(sorted(s)) for s in sig_a.values())
    multiset_b = sorted(tuple(sorted(s)) for s in sig_b.values())
    assert multiset_a == multiset_b


# -------------------- Lossy-property documentation tests --------------------


def test_round_trip_drops_is_power_flag() -> None:
    original = _flagged_two_resistor_schematic()
    for n in original.nets:
        if n.name == "vin":
            n.is_power = True
    parsed = parse_asc_text(emit_asc(original))
    parsed_vin = next(n for n in parsed.nets if n.name == "vin")
    assert parsed_vin.is_power is False  # documented loss; emitter has no convention


def test_round_trip_drops_standard_spice_prefix() -> None:
    """Standard prefixes (R/C/L/V/I/D/Q/M) are not written by the emitter."""
    original = _flagged_two_resistor_schematic()
    parsed = parse_asc_text(emit_asc(original))
    r1_parsed = parsed.component_by_ref("R1")
    assert r1_parsed.spice_prefix is None  # documented loss


def test_round_trip_preserves_nonstandard_spice_prefix() -> None:
    """Non-standard prefixes (e.g. 'B', 'E') ARE written and round-trip."""
    original = _flagged_two_resistor_schematic()
    original.component_by_ref("R1").spice_prefix = "B"
    parsed = parse_asc_text(emit_asc(original))
    assert parsed.component_by_ref("R1").spice_prefix == "B"
