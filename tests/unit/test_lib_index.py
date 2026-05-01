"""Tests for the LTspice ``.asy`` library reader."""

from __future__ import annotations

from pathlib import Path

import pytest

from wirewright.symbols.lib_index import (
    default_ltspice_lib_path,
    parse_asy_file,
    parse_asy_pins_by_spice_order,
)

_RES_ASY = """\
Version 4
SymbolType CELL
LINE Normal 16 88 16 96
LINE Normal 0 80 16 88
LINE Normal 32 64 0 80
LINE Normal 0 48 32 64
LINE Normal 32 32 0 48
LINE Normal 16 16 16 24
LINE Normal 16 24 32 32
WINDOW 0 36 40 Left 2
WINDOW 3 36 76 Left 2
SYMATTR Value R
SYMATTR Prefix R
SYMATTR Description A resistor
PIN 16 16 NONE 0
PINATTR PinName A
PINATTR SpiceOrder 1
PIN 16 96 NONE 0
PINATTR PinName B
PINATTR SpiceOrder 2
"""

_BV_ASY = """\
Version 4
SymbolType CELL
CIRCLE Normal -32 24 32 88
PIN 0 16 NONE 0
PINATTR PinName +
PINATTR SpiceOrder 1
PIN 0 96 NONE 0
PINATTR PinName -
PINATTR SpiceOrder 2
"""


def test_parse_asy_uses_pin_names(tmp_path: Path) -> None:
    p = tmp_path / "res.asy"
    p.write_text(_RES_ASY)
    g = parse_asy_file(p)
    assert g.name == "res"
    assert g.pins == {"A": (16, 16), "B": (16, 96)}


def test_parse_asy_handles_signed_coords(tmp_path: Path) -> None:
    p = tmp_path / "bv.asy"
    p.write_text(_BV_ASY)
    g = parse_asy_file(p)
    assert g.pins == {"+": (0, 16), "-": (0, 96)}
    # Bbox includes the circle extending to x=-32.
    assert g.bbox[0] == -32


def test_parse_asy_pins_by_spice_order(tmp_path: Path) -> None:
    p = tmp_path / "res.asy"
    p.write_text(_RES_ASY)
    assert parse_asy_pins_by_spice_order(p) == {1: (16, 16), 2: (16, 96)}


def test_parse_asy_raises_when_no_pins(tmp_path: Path) -> None:
    p = tmp_path / "empty.asy"
    p.write_text("Version 4\nSymbolType CELL\n")
    with pytest.raises(ValueError, match="No PIN blocks"):
        parse_asy_file(p)


def test_default_path_respects_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WIREWRIGHT_LTSPICE_LIB", str(tmp_path))
    assert default_ltspice_lib_path() == tmp_path


def test_default_path_returns_none_when_override_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bogus = tmp_path / "does-not-exist"
    monkeypatch.setenv("WIREWRIGHT_LTSPICE_LIB", str(bogus))
    assert default_ltspice_lib_path() is None


def test_resolve_asy_path_finds_root_symbol() -> None:
    from wirewright.symbols.lib_index import resolve_asy_path

    p = resolve_asy_path("res")
    if p is None:
        pytest.skip("LTspice library not found")
    assert p.name == "res.asy"


def test_resolve_asy_path_finds_subfolder_symbol() -> None:
    from wirewright.symbols.lib_index import resolve_asy_path

    p = resolve_asy_path("opamp2")
    if p is None:
        pytest.skip("LTspice library not found or opamp2 missing")
    assert p.parent.name == "OpAmps"


def test_resolve_asy_path_accepts_prefixed_name() -> None:
    from wirewright.symbols.lib_index import resolve_asy_path

    bare = resolve_asy_path("opamp2")
    prefixed = resolve_asy_path("OpAmps/opamp2")
    if bare is None:
        pytest.skip("LTspice library not found")
    assert bare == prefixed


def test_resolve_asy_path_returns_none_for_unknown() -> None:
    from wirewright.symbols.lib_index import resolve_asy_path

    assert resolve_asy_path("does_not_exist_anywhere") is None
