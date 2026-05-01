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


class TestSubcktStructuralErrors:
    def test_nested_subckt_rejected(self) -> None:
        text = ".subckt A IN OUT\n.subckt B IN OUT\n.ends B\n.ends A\n"
        with pytest.raises(ParseError, match="nested .SUBCKT"):
            parse_spice_text(text)

    def test_unclosed_subckt_rejected(self) -> None:
        text = ".subckt A IN OUT\nR1 IN OUT 1k\n"
        with pytest.raises(ParseError, match="not closed by .ENDS"):
            parse_spice_text(text)

    def test_orphan_ends_rejected(self) -> None:
        with pytest.raises(ParseError, match="without matching"):
            parse_spice_text(".ends FOO\n")

    def test_local_model_rejected(self) -> None:
        text = ".subckt A IN OUT\n.model FOO NPN()\n.ends A\n"
        with pytest.raises(ParseError, match="local .MODEL"):
            parse_spice_text(text)


class TestBjt:
    def test_q_card_with_npn_model(self) -> None:
        text = ".model QN3904 NPN(IS=6.7e-15)\nQ1 col base emit QN3904\n.end\n"
        c = _by_ref(text, "Q1")
        assert c.symbol == "npn"
        assert c.spice_prefix == "Q"
        assert c.spice_model == "QN3904"
        assert c.pins == {"C": "col", "B": "base", "E": "emit"}

    def test_q_card_with_pnp_model(self) -> None:
        text = ".model QP3906 PNP(IS=4.5e-16)\nQ_X c b e QP3906\n.end\n"
        c = _by_ref(text, "Q_X")
        assert c.symbol == "pnp"

    def test_q_card_with_unknown_model_raises(self) -> None:
        with pytest.raises(ParseError, match="unknown BJT model"):
            parse_spice_text("Q1 c b e MISSING_MODEL\n.end\n")

    def test_q_card_4node_substrate_form_rejected(self) -> None:
        text = ".model QN3904 NPN()\nQ1 c b e sub QN3904\n.end\n"
        with pytest.raises(ParseError, match="4-node"):
            parse_spice_text(text)


class TestMosfet:
    def test_m_card_4pin_nmos(self) -> None:
        text = ".model NM NMOS()\nM1 d g s b NM\n.end\n"
        c = _by_ref(text, "M1")
        assert c.symbol == "nmos4"
        assert c.pins == {"D": "d", "G": "g", "S": "s", "B": "b"}

    def test_m_card_3pin_pmos(self) -> None:
        text = ".model PM PMOS()\nM2 d g s PM\n.end\n"
        c = _by_ref(text, "M2")
        assert c.symbol == "pmos"
        assert c.pins == {"D": "d", "G": "g", "S": "s"}

    def test_m_card_unknown_model_raises(self) -> None:
        with pytest.raises(ParseError, match="unknown MOSFET model"):
            parse_spice_text("M1 d g s b NOSUCH\n.end\n")


class TestCurrentSource:
    def test_i_card_two_terminal(self) -> None:
        c = _by_ref("I1 vcc 0 1m\n.end\n", "I1")
        assert c.symbol == "current"
        assert c.spice_prefix == "I"
        assert c.pins == {"+": "vcc", "-": "0"}
        assert c.value == "1m"


class TestVcSwitch:
    def test_s_card_four_terminal(self) -> None:
        text = ".model SW1 SW(VT=0.5)\nS1 a b c d SW1\n.end\n"
        c = _by_ref(text, "S1")
        assert c.symbol == "sw"
        assert c.spice_prefix == "S"
        assert c.spice_model == "SW1"
        assert c.pins == {"A": "a", "B": "b", "NC+": "c", "NC-": "d"}

    def test_s_card_unknown_model_raises(self) -> None:
        with pytest.raises(ParseError, match="unknown switch model"):
            parse_spice_text("S1 a b c d NOSUCH\n.end\n")


class TestSubcircuit:
    def test_simple_x_inlines_subckt_body_with_x_stripped_prefix(self) -> None:
        text = ".subckt INV IN OUT\nR1 IN OUT 10k\n.ends INV\nXU1 vin vout INV\n.end\n"
        sch = parse_spice_text(text)
        c = sch.component_by_ref("U1.R1")
        assert c.symbol == "res"
        assert c.pins == {"1": "vin", "2": "vout"}

    def test_internal_nets_get_namespace_prefix(self) -> None:
        text = (
            ".subckt DIV IN OUT\nR1 IN MID 10k\nR2 MID OUT 10k\n.ends DIV\nXD vin vout DIV\n.end\n"
        )
        sch = parse_spice_text(text)
        r1 = sch.component_by_ref("D.R1")
        r2 = sch.component_by_ref("D.R2")
        assert r1.pins == {"1": "vin", "2": "D.MID"}
        assert r2.pins == {"1": "D.MID", "2": "vout"}

    def test_unknown_subckt_raises(self) -> None:
        with pytest.raises(ParseError, match="unknown subcircuit"):
            parse_spice_text("XU1 a b NOSUCH\n.end\n")

    def test_arity_mismatch_raises(self) -> None:
        text = ".subckt TWO_PORT A B\nR1 A B 1k\n.ends TWO_PORT\nXU1 vin TWO_PORT\n.end\n"
        with pytest.raises(ParseError, match="port"):
            parse_spice_text(text)

    def test_self_recursion_rejected(self) -> None:
        text = ".subckt SELF A B\nXINNER A B SELF\n.ends SELF\nXU1 a b SELF\n.end\n"
        with pytest.raises(ParseError, match="recursion"):
            parse_spice_text(text)


class TestVcoIntegratedFixture:
    """End-to-end on tests/fixtures/hard/tb303-vco-integrated.net.

    Fixtures are gitignored (local-only); skipped when the file is absent.
    """

    def test_fixture_parses_without_error(self) -> None:
        from pathlib import Path

        from wirewright.parse.spice import parse_spice_file

        path = Path(__file__).parent.parent / "fixtures/hard/tb303-vco-integrated.net"
        if not path.exists():
            pytest.skip(f"local fixture not present: {path.name}")
        sch = parse_spice_file(path)
        refs = {c.ref for c in sch.components}

        # At least 5 BJTs (the fixture has 7 NPN/PNP transistors).
        bjt_refs = [r for r in refs if r.startswith("Q")]
        assert len(bjt_refs) >= 5, f"expected ≥5 BJTs, got {bjt_refs}"

        # OPAMP body has 2 components (BAMP, ROUT). Flattened with U_SQR. prefix.
        u_sqr_refs = sorted(r for r in refs if r.startswith("U_SQR."))
        assert u_sqr_refs == ["U_SQR.BAMP", "U_SQR.ROUT"], (
            f"OPAMP flatten produced wrong refs: {u_sqr_refs}"
        )

        # The S handler ran (fixture has S_DISCH using SW model).
        assert "S_DISCH" in refs

        # The original X line is gone after flattening.
        assert "XU_SQR" not in refs


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
