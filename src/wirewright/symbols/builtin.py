"""Hand-curated pin offsets for common LTspice symbols.

WARNING: these values are approximations based on the standard LTspice
library. Phase 1 will verify them against actual ``.asy`` files. Until then,
expect minor pin-misalignment issues for some symbols. The grid_naive placer
and the demo only use ``res``, which is verified.

Each symbol's pin offsets are given in IR units (1 unit = 1 mil; LTspice
grid = 16 units), measured from the symbol's R0 origin (top-left of the
symbol's bounding region in LTspice convention).

To verify: open ``~/Library/Application Support/LTspice/lib/sym/<name>.asy``
in a text editor and look for ``PIN x y NONE 0`` lines.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolGeometry:
    """Pin offsets and bounding box for one symbol in R0 orientation."""

    name: str
    pins: dict[str, tuple[int, int]]
    """Pin name to (x, y) offset from symbol origin under R0."""

    bbox: tuple[int, int, int, int]
    """(x_min, y_min, x_max, y_max) of the symbol's drawn region under R0."""


# ---------------------------------------------------------------------------
# Verified against LTspice XVII standard library:
# ---------------------------------------------------------------------------

_RES = SymbolGeometry(
    name="res",
    pins={"1": (16, 0), "2": (16, 80)},
    bbox=(-16, 0, 48, 80),
)

# ---------------------------------------------------------------------------
# Approximate. TODO Phase 1: verify against .asy files.
# ---------------------------------------------------------------------------

_CAP = SymbolGeometry(
    name="cap",
    pins={"1": (16, 0), "2": (16, 64)},
    bbox=(-16, 0, 48, 64),
)

_POLCAP = SymbolGeometry(
    name="polcap",
    pins={"1": (16, 0), "2": (16, 64)},
    bbox=(-16, 0, 48, 64),
)

_IND = SymbolGeometry(
    name="ind",
    pins={"1": (16, 0), "2": (16, 80)},
    bbox=(-16, 0, 48, 80),
)

_DIODE = SymbolGeometry(
    name="diode",
    pins={"A": (16, 0), "K": (16, 64)},
    bbox=(-16, 0, 48, 64),
)

_NPN = SymbolGeometry(
    name="npn",
    pins={"C": (64, 0), "B": (0, 48), "E": (64, 96)},
    bbox=(0, 0, 96, 96),
)

_PNP = SymbolGeometry(
    name="pnp",
    pins={"E": (64, 0), "B": (0, 48), "C": (64, 96)},
    bbox=(0, 0, 96, 96),
)

_NMOS = SymbolGeometry(
    name="nmos",
    pins={"D": (64, 0), "G": (0, 48), "S": (64, 96), "B": (64, 48)},
    bbox=(0, 0, 96, 96),
)

_PMOS = SymbolGeometry(
    name="pmos",
    pins={"D": (64, 96), "G": (0, 48), "S": (64, 0), "B": (64, 48)},
    bbox=(0, 0, 96, 96),
)

_OPAMP2 = SymbolGeometry(
    name="opamp2",
    pins={"+": (0, 32), "-": (0, 96), "OUT": (128, 64), "V+": (64, 0), "V-": (64, 128)},
    bbox=(0, 0, 128, 128),
)

_VOLTAGE = SymbolGeometry(
    name="voltage",
    pins={"+": (0, 0), "-": (0, 80)},
    bbox=(-32, 0, 32, 80),
)

_CURRENT = SymbolGeometry(
    name="current",
    pins={"+": (0, 0), "-": (0, 80)},
    bbox=(-32, 0, 32, 80),
)


_REGISTRY: dict[str, SymbolGeometry] = {
    g.name: g
    for g in [
        _RES,
        _CAP,
        _POLCAP,
        _IND,
        _DIODE,
        _NPN,
        _PNP,
        _NMOS,
        _PMOS,
        _OPAMP2,
        _VOLTAGE,
        _CURRENT,
    ]
}


def symbol_geometry(symbol: str) -> SymbolGeometry:
    """Return the geometry record for a symbol name. Raises KeyError if unknown."""
    try:
        return _REGISTRY[symbol]
    except KeyError as e:
        raise KeyError(f"Unknown symbol {symbol!r}. Known symbols: {sorted(_REGISTRY)}") from e


def pin_offset(symbol: str, pin: str) -> tuple[int, int]:
    """Return the (dx, dy) pin offset for a pin in R0 orientation.

    Apply :func:`rotate_offset` to convert to other orientations.
    """
    geo = symbol_geometry(symbol)
    try:
        return geo.pins[pin]
    except KeyError as e:
        raise KeyError(
            f"Symbol {symbol!r} has no pin named {pin!r}. Known pins: {sorted(geo.pins)}"
        ) from e


def rotate_offset(offset: tuple[int, int], orientation: str) -> tuple[int, int]:
    """Rotate or mirror a pin offset to match a symbol orientation.

    LTspice symbol orientations (R0, R90, R180, R270, M0, M90, M180, M270) are
    transformations applied around the symbol's origin. This function takes a
    pin offset under R0 and returns the offset under the given orientation,
    keeping the result aligned to the LTspice grid.
    """
    dx, dy = offset
    match orientation:
        case "R0":
            return (dx, dy)
        case "R90":
            return (-dy, dx)
        case "R180":
            return (-dx, -dy)
        case "R270":
            return (dy, -dx)
        case "M0":
            # Mirror across vertical axis (flip x).
            return (-dx, dy)
        case "M90":
            # Mirror then rotate 90.
            return (-dy, -dx)
        case "M180":
            return (dx, -dy)
        case "M270":
            return (dy, dx)
        case _:
            raise ValueError(f"Unknown orientation: {orientation!r}")


def absolute_pin_position(
    component_origin: tuple[int, int],
    symbol: str,
    pin: str,
    orientation: str,
) -> tuple[int, int]:
    """Compute the canvas-absolute position of a pin on a placed component."""
    cx, cy = component_origin
    dx, dy = rotate_offset(pin_offset(symbol, pin), orientation)
    return (cx + dx, cy + dy)
