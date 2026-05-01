"""Tests for the LTspice .asc parser."""

from __future__ import annotations

import warnings

import pytest

from wirewright.parse.ltspice_asc import AscParseError, parse_asc_text


def test_empty_asc_returns_empty_schematic() -> None:
    sch = parse_asc_text("Version 4\nSHEET 1 880 680\n")
    assert sch.components == []
    assert sch.nets == []
    assert sch.wires == []
    assert sch.flags == []


def test_missing_version_header_raises() -> None:
    with pytest.raises(AscParseError, match="Version"):
        parse_asc_text("SHEET 1 880 680\n")


_CLEAN_TWO_RESISTOR_ASC = """\
Version 4
SHEET 1 416 320
WIRE 80 80 80 48
WIRE 80 48 272 48
WIRE 272 48 272 80
FLAG 80 160 vin
FLAG 80 48 n1
FLAG 272 160 0
SYMBOL res 64 64 R0
SYMATTR InstName R1
SYMATTR Value 10k
SYMBOL res 256 64 R0
SYMATTR InstName R2
SYMATTR Value 10k
TEXT 128 240 Left 2 !.tran 1m
"""


def test_clean_asc_recovers_components() -> None:
    sch = parse_asc_text(_CLEAN_TWO_RESISTOR_ASC)
    refs = {c.ref for c in sch.components}
    assert refs == {"R1", "R2"}
    r1 = sch.component_by_ref("R1")
    assert r1.symbol == "res"
    assert r1.value == "10k"
    assert (r1.x, r1.y, r1.orientation) == (64, 64, "R0")


def test_clean_asc_recovers_wires() -> None:
    sch = parse_asc_text(_CLEAN_TWO_RESISTOR_ASC)
    assert {(w.x1, w.y1, w.x2, w.y2) for w in sch.wires} == {
        (80, 80, 80, 48),
        (80, 48, 272, 48),
        (272, 48, 272, 80),
    }


def test_clean_asc_recovers_flags() -> None:
    sch = parse_asc_text(_CLEAN_TWO_RESISTOR_ASC)
    assert {(f.x, f.y, f.net) for f in sch.flags} == {
        (80, 160, "vin"),
        (80, 48, "n1"),
        (272, 160, "0"),
    }


def test_clean_asc_recovers_directives() -> None:
    sch = parse_asc_text(_CLEAN_TWO_RESISTOR_ASC)
    assert sch.directives == [".tran 1m"]


def test_clean_asc_recovers_nets_via_connectivity() -> None:
    sch = parse_asc_text(_CLEAN_TWO_RESISTOR_ASC)
    assert {n.name for n in sch.nets} == {"vin", "n1", "0"}
    r1 = sch.component_by_ref("R1")
    r2 = sch.component_by_ref("R2")
    assert r1.pins == {"1": "n1", "2": "vin"}
    assert r2.pins == {"1": "n1", "2": "0"}


def test_non_axis_aligned_wire_raises_with_line_context() -> None:
    bad = "Version 4\nSHEET 1 880 680\nWIRE 80 80 100 100\n"
    with pytest.raises(AscParseError, match="line 3"):
        parse_asc_text(bad)


def test_unknown_symattr_emits_warning() -> None:
    asc = (
        "Version 4\nSHEET 1 880 680\nSYMBOL res 64 64 R0\nSYMATTR InstName R1\nSYMATTR FooBar baz\n"
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        parse_asc_text(asc)
    assert any("FooBar" in str(rec.message) for rec in w)


def test_unknown_line_type_emits_warning() -> None:
    asc = "Version 4\nSHEET 1 880 680\nBUSTAP 0 0 0 16\n"
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        parse_asc_text(asc)
    assert any("BUSTAP" in str(rec.message) for rec in w)


def test_lib_folder_prefix_stripped_for_registry_lookup() -> None:
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "FLAG 0 64 inv\nFLAG 0 96 noninv\nFLAG 64 80 out\n"
        "SYMBOL OpAmps/opamp 32 16 R0\nSYMATTR InstName U1\n"
    )
    sch = parse_asc_text(asc)
    u1 = sch.component_by_ref("U1")
    assert u1.symbol == "OpAmps/opamp"  # full path preserved on the component
    # Pin connectivity recovered via _strip_lib_folder during registry lookup.
    assert "invin" in u1.pins
    assert "noninvin" in u1.pins
    assert "out" in u1.pins


def test_conflicting_flag_names_warn_first_wins() -> None:
    asc = (
        "Version 4\nSHEET 1 880 680\n"
        "WIRE 80 80 80 96\n"
        "FLAG 80 80 alpha\n"
        "FLAG 80 96 beta\n"
        "SYMBOL res 64 64 R0\nSYMATTR InstName R1\nSYMATTR Value 10k\n"
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sch = parse_asc_text(asc)
    r1 = sch.component_by_ref("R1")
    # First flag (alpha at (80, 80)) wins for the connected component.
    assert "alpha" in r1.pins.values()
    assert any("alpha" in str(rec.message) and "beta" in str(rec.message) for rec in w)
