"""Resolve and parse LTspice ``.asy`` symbol files.

The LTspice symbol library is not part of this repo: it lives in the user's
LTspice install. We need to read individual ``.asy`` files to verify (and
eventually scan) the pin offsets in :mod:`wirewright.symbols.builtin`.

Default lib/sym location:
1. ``WIREWRIGHT_LTSPICE_LIB`` env var (overrides everything).
2. Per-OS default:
   - macOS: ``~/Library/Application Support/LTspice/lib/sym/``
   - Windows: ``%USERPROFILE%/AppData/Local/LTspice/lib/sym/``
3. None on Linux/unknown — set the env var.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from wirewright.symbols.builtin import SymbolGeometry

_PER_OS_DEFAULT: dict[str, str] = {
    "darwin": "Library/Application Support/LTspice/lib/sym",
    "win32": "AppData/Local/LTspice/lib/sym",
}


def default_ltspice_lib_path() -> Path | None:
    """Return the user's LTspice ``lib/sym`` directory, or None if not found."""
    override = os.environ.get("WIREWRIGHT_LTSPICE_LIB")
    if override:
        path = Path(override).expanduser()
        return path if path.is_dir() else None
    relative = _PER_OS_DEFAULT.get(sys.platform)
    if relative is None:
        return None
    path = Path.home() / relative
    return path if path.is_dir() else None


_PIN_BLOCK_RE = re.compile(
    r"^PIN\s+(-?\d+)\s+(-?\d+)\s+\S+\s+\d+\s*\n"
    r"PINATTR\s+PinName\s+(\S+)\s*\n"
    r"PINATTR\s+SpiceOrder\s+(\d+)",
    re.MULTILINE,
)


def parse_asy_file(path: str | Path) -> SymbolGeometry:
    """Parse an LTspice ``.asy`` file into a :class:`SymbolGeometry`.

    Pins are taken from ``PIN x y NONE n`` blocks paired with
    ``PINATTR PinName <name>`` and ``PINATTR SpiceOrder <n>``. The bounding
    box covers all ``LINE``/``CIRCLE``/``RECTANGLE`` primitives plus the pins.

    Pin keys in the returned record are the ``PinName`` strings exactly as they
    appear in the ``.asy`` (e.g. ``A``/``B`` for resistors, ``+``/``-`` for
    behavioral sources). Callers that want SpiceOrder indexing should use
    :func:`parse_asy_pins_by_spice_order` instead.
    """
    path = Path(path)
    text = path.read_text()
    name = path.stem

    pins: dict[str, tuple[int, int]] = {}
    for m in _PIN_BLOCK_RE.finditer(text):
        pins[m.group(3)] = (int(m.group(1)), int(m.group(2)))

    if not pins:
        raise ValueError(f"No PIN blocks found in {path}")

    bbox = _compute_bbox(text, pins)
    return SymbolGeometry(name=name, pins=pins, bbox=bbox)


_SUBFOLDERS_TO_SEARCH: tuple[str, ...] = ("", "OpAmps", "Comparators", "Digital")


def resolve_asy_path(name: str, lib: Path | None = None) -> Path | None:
    """Locate the ``.asy`` file for a symbol name within the LTspice library.

    Tries the lib root first, then known subfolders (``OpAmps/``, ``Comparators/``,
    ``Digital/``). Accepts ``name`` with or without a leading folder prefix
    (e.g. ``"opamp2"`` and ``"OpAmps/opamp2"`` both resolve to the same path).

    Returns None when the library is not found or the symbol isn't there.
    """
    if lib is None:
        lib = default_ltspice_lib_path()
    if lib is None:
        return None
    bare = name.split("/")[-1]
    for folder in _SUBFOLDERS_TO_SEARCH:
        candidate = (lib / folder / f"{bare}.asy") if folder else (lib / f"{bare}.asy")
        if candidate.is_file():
            return candidate
    return None


def parse_asy_pins_by_spice_order(path: str | Path) -> dict[int, tuple[int, int]]:
    """Return ``{spice_order_int: (x, y)}`` for every pin in the ``.asy``."""
    text = Path(path).read_text()
    out: dict[int, tuple[int, int]] = {}
    for m in _PIN_BLOCK_RE.finditer(text):
        out[int(m.group(4))] = (int(m.group(1)), int(m.group(2)))
    if not out:
        raise ValueError(f"No PIN blocks found in {path}")
    return out


def _compute_bbox(text: str, pins: dict[str, tuple[int, int]]) -> tuple[int, int, int, int]:
    xs: list[int] = [p[0] for p in pins.values()]
    ys: list[int] = [p[1] for p in pins.values()]
    for line in text.splitlines():
        tokens = line.split()
        if len(tokens) < 6:
            continue
        if tokens[0] in ("LINE", "CIRCLE", "RECTANGLE", "ARC"):
            # Bounding rectangle of LINE/CIRCLE/RECTANGLE/ARC is in tokens[2..5];
            # ARC has additional sweep-point tokens we don't need for bbox.
            xs.extend([int(tokens[2]), int(tokens[4])])
            ys.extend([int(tokens[3]), int(tokens[5])])
    return (min(xs), min(ys), max(xs), max(ys))
