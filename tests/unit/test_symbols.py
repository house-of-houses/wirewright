"""Tests for the symbol geometry registry."""

from __future__ import annotations

import pytest

from wirewright.symbols import pin_offset, rotate_offset, symbol_geometry
from wirewright.symbols.builtin import absolute_pin_position


def test_resistor_pins() -> None:
    assert pin_offset("res", "1") == (16, 0)
    assert pin_offset("res", "2") == (16, 80)


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
    assert pos == (116, 280)


def test_absolute_pin_position_with_rotation() -> None:
    # Resistor pin 2 is at (16, 80) under R0. Under R90 (clockwise), it
    # rotates to (-80, 16) relative to the symbol origin.
    pos = absolute_pin_position((100, 200), "res", "2", "R90")
    assert pos == (100 - 80, 200 + 16)
