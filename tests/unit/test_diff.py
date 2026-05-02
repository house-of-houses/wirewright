"""Tests for the .asc structural diff."""

from __future__ import annotations

from wirewright.diff import diff_asc_files

_BASE = """\
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
"""


def test_no_changes_diff_is_empty() -> None:
    d = diff_asc_files(_BASE, _BASE)
    assert d.moved == []
    assert d.rotated == []
    assert d.connectivity_preserved


def test_component_move_detected() -> None:
    edited = _BASE.replace("SYMBOL res 256 64 R0", "SYMBOL res 320 96 R0")
    # The move shifts R2's pins, which moves where flags/wires need to land
    # for connectivity. The diff_asc files only compare what's IN the file.
    # Topology will likely change too because the pins moved away from the
    # original wire endpoints. Assert we at least see the component move.
    d = diff_asc_files(_BASE, edited)
    moves = {m.ref: m for m in d.moved}
    assert "R2" in moves
    assert moves["R2"].old_xy == (256, 64)
    assert moves["R2"].new_xy == (320, 96)


def test_component_rotation_detected() -> None:
    edited = _BASE.replace("SYMBOL res 256 64 R0", "SYMBOL res 256 64 R90")
    d = diff_asc_files(_BASE, edited)
    rots = {r.ref: r for r in d.rotated}
    assert "R2" in rots
    assert (rots["R2"].old_orientation, rots["R2"].new_orientation) == ("R0", "R90")


def test_wire_added_detected() -> None:
    edited = _BASE.rstrip() + "\nWIRE 100 200 200 200\n"
    d = diff_asc_files(_BASE, edited)
    assert d.wires_added == 1
    assert d.wires_removed == 0


def test_wire_removed_detected() -> None:
    edited = _BASE.replace("WIRE 80 48 272 48\n", "")
    d = diff_asc_files(_BASE, edited)
    assert d.wires_added == 0
    assert d.wires_removed == 1
