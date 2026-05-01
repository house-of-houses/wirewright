"""Tests for the SPICE netlist parser.

See docs/specs/netlist-parser.md for the contract.
"""

from __future__ import annotations

import pytest

from wirewright.parse.spice import ParseError, parse_spice_text


def _by_ref(text: str, ref: str):
    sch = parse_spice_text(text)
    return sch.component_by_ref(ref)


class TestDiode:
    def test_d_card_maps_to_diode_with_anode_cathode_pins(self) -> None:
        c = _by_ref("D1 anode cath DFAST\n.end\n", "D1")
        assert c.symbol == "diode"
        assert c.spice_prefix == "D"
        assert c.spice_model == "DFAST"
        assert c.pins == {"A": "anode", "K": "cath"}

    def test_d_card_without_model_raises(self) -> None:
        with pytest.raises(ParseError, match="line 1"):
            parse_spice_text("D1 a b\n")


class TestBehavioralSource:
    def test_b_voltage_single_line(self) -> None:
        c = _by_ref("B1 out 0 V=V(in)*2\n.end\n", "B1")
        assert c.symbol == "bv"
        assert c.spice_prefix == "B"
        assert c.pins == {"+": "out", "-": "0"}
        assert c.value == "V=V(in)*2"

    def test_b_current_uses_bi_symbol(self) -> None:
        c = _by_ref("B2 a b I=V(c)*10u\n.end\n", "B2")
        assert c.symbol == "bi"
        assert c.value == "I=V(c)*10u"

    def test_b_with_continuation_joins_value(self) -> None:
        text = "B_GATE GATE 0 V=5*(\n+ (time>=0 & time<50m) +\n+ (time>=500m & time<600m))\n.end\n"
        c = _by_ref(text, "B_GATE")
        assert c.symbol == "bv"
        assert c.pins == {"+": "GATE", "-": "0"}
        # Continuations are joined with a single space; the V=... expression
        # is preserved verbatim apart from line breaks.
        assert c.value is not None
        assert "5*(" in c.value
        assert "(time>=500m & time<600m))" in c.value
        assert "\n" not in c.value


class TestVcvs:
    def test_e_card_four_terminal(self) -> None:
        c = _by_ref("E1 outp outn ctrlp ctrln 1\n.end\n", "E1")
        assert c.symbol == "e"
        assert c.spice_prefix == "E"
        assert c.pins == {"+": "outp", "-": "outn", "P": "ctrlp", "N": "ctrln"}
        assert c.value == "1"

    def test_e_card_too_few_terminals_raises(self) -> None:
        with pytest.raises(ParseError, match="line 1"):
            parse_spice_text("E1 a b c\n")


class TestContinuation:
    def test_blank_line_breaks_continuation(self) -> None:
        # A blank line between the card and a `+` should make the `+` line
        # an orphan continuation, which is a parse error.
        text = "B1 a b V=1\n\n+ unrelated\n"
        with pytest.raises(ParseError, match="orphan"):
            parse_spice_text(text)

    def test_comment_between_continuations_is_skipped(self) -> None:
        text = "B1 a b V=1\n* a comment in the middle\n+ +2\n.end\n"
        c = _by_ref(text, "B1")
        assert c.value == "V=1 +2"


class TestEnvelopeFixture:
    """End-to-end on tests/fixtures/medium/tb303-envelope.net.

    Fixtures are gitignored (local-only); skipped when the file is absent.
    """

    def test_fixture_parses_without_error(self) -> None:
        from pathlib import Path

        from wirewright.parse.spice import parse_spice_file

        path = Path(__file__).parent.parent / "fixtures/medium/tb303-envelope.net"
        if not path.exists():
            pytest.skip(f"local fixture not present: {path.name}")
        sch = parse_spice_file(path)
        # 10 R + 2 C + 2 D + 4 B + 2 E = 20 components.
        assert len(sch.components) == 20
        # Spot-check one of each new element type.
        d_vcf = sch.component_by_ref("D_VCF")
        assert d_vcf.symbol == "diode"
        assert d_vcf.spice_model == "DFAST"
        b_drive = sch.component_by_ref("B_VCF_DRIVE")
        assert b_drive.symbol == "bv"
        assert b_drive.value is not None
        assert "V(GATE)" in b_drive.value
        e_buf = sch.component_by_ref("E_VCF_BUF")
        assert e_buf.symbol == "e"
        assert e_buf.pins["+"] == "VCF_OUT"
