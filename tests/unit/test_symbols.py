"""Tests for the symbol geometry registry."""

from __future__ import annotations

import pytest

from wirewright.symbols import pin_offset, rotate_offset, symbol_geometry
from wirewright.symbols.builtin import UNVERIFIED_SYMBOLS, absolute_pin_position
from wirewright.symbols.lib_index import (
    parse_asy_file,
    parse_asy_pins_by_spice_order,
    resolve_asy_path,
)


def test_resistor_pins() -> None:
    # Pin offsets verified against res.asy: PIN 16 16 / PIN 16 96.
    assert pin_offset("res", "1") == (16, 16)
    assert pin_offset("res", "2") == (16, 96)


def test_unknown_symbol_raises() -> None:
    with pytest.raises(KeyError, match="Unknown symbol 'flux_capacitor'"):
        symbol_geometry("flux_capacitor")


def test_unknown_pin_raises() -> None:
    with pytest.raises(KeyError, match="has no pin named 'X'"):
        pin_offset("res", "X")


@pytest.mark.parametrize(
    "orientation,expected",
    [
        ("R0", (16, 0)),
        ("R90", (0, 16)),
        ("R180", (-16, 0)),
        ("R270", (0, -16)),
        ("M0", (-16, 0)),
        ("M180", (16, 0)),
    ],
)
def test_rotate_offset(orientation: str, expected: tuple[int, int]) -> None:
    assert rotate_offset((16, 0), orientation) == expected


def test_absolute_pin_position_combines_origin_and_rotation() -> None:
    pos = absolute_pin_position((100, 200), "res", "2", "R0")
    assert pos == (116, 296)


def test_absolute_pin_position_with_rotation() -> None:
    # Resistor pin 2 is at (16, 96) under R0; under R90 that rotates to
    # (-96, 16) relative to the symbol origin.
    pos = absolute_pin_position((100, 200), "res", "2", "R90")
    assert pos == (100 - 96, 200 + 16)


# ----------------------------------------------------------------------------
# Pin-offset audit against the real LTspice .asy library.
# ----------------------------------------------------------------------------

# Maps IR pin name to the symbol's SpiceOrder index, per registered symbol.
# The audit reads each .asy by SpiceOrder and reconstructs the expected IR
# offset dict, so a name-vs-index mismatch (e.g. C/E swapped on PNP) fails.
_SPICE_ORDER_BY_SYMBOL: dict[str, dict[str, int]] = {
    "res": {"1": 1, "2": 2},
    "ind": {"1": 1, "2": 2},
    "cap": {"1": 1, "2": 2},
    "polcap": {"1": 1, "2": 2},
    "diode": {"A": 1, "K": 2},
    "npn": {"C": 1, "B": 2, "E": 3},
    "pnp": {"C": 1, "B": 2, "E": 3},
    "voltage": {"+": 1, "-": 2},
    "current": {"+": 1, "-": 2},
    "bv": {"+": 1, "-": 2},
    "e": {"+": 1, "-": 2, "P": 3, "N": 4},
    "nmos": {"D": 1, "G": 2, "S": 3},
    "nmos4": {"D": 1, "G": 2, "S": 3, "B": 4},
    "pmos": {"D": 1, "G": 2, "S": 3},
    "pmos4": {"D": 1, "G": 2, "S": 3, "B": 4},
    "opamp": {"invin": 1, "noninvin": 2, "out": 3},
    "opamp2": {"In+": 1, "In-": 2, "V+": 3, "V-": 4, "OUT": 5},
    "sw": {"A": 1, "B": 2, "NC+": 3, "NC-": 4},
}


@pytest.mark.parametrize("name", sorted(_SPICE_ORDER_BY_SYMBOL))
def test_pin_offsets_match_asy_file(name: str) -> None:
    """Each verified symbol's pin offsets match the real LTspice ``.asy``.

    Skipped when no LTspice install is found; set ``WIREWRIGHT_LTSPICE_LIB``
    to enable on machines where the default path doesn't exist.
    """
    if name in UNVERIFIED_SYMBOLS:
        pytest.skip(f"{name} is flagged unverified in builtin.py")
    asy_path = resolve_asy_path(name)
    if asy_path is None:
        pytest.skip(f"{name}.asy not present in this LTspice install")

    asy_by_order = parse_asy_pins_by_spice_order(asy_path)
    expected = {
        ir_name: asy_by_order[order] for ir_name, order in _SPICE_ORDER_BY_SYMBOL[name].items()
    }
    assert symbol_geometry(name).pins == expected


@pytest.mark.parametrize("name", sorted(_SPICE_ORDER_BY_SYMBOL))
def test_pin_bboxes_match_asy_file(name: str) -> None:
    """Each verified symbol's bbox matches what parse_asy_file would extract."""
    if name in UNVERIFIED_SYMBOLS:
        pytest.skip(f"{name} is flagged unverified in builtin.py")
    asy_path = resolve_asy_path(name)
    if asy_path is None:
        pytest.skip(f"{name}.asy not present in this LTspice install")
    expected = parse_asy_file(asy_path).bbox
    assert symbol_geometry(name).bbox == expected
