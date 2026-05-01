"""Hand-curated pin offsets for common LTspice symbols.

Pin offsets are in IR units (1 unit = 1 mil; LTspice grid = 16 units), measured
from the symbol's R0 origin (top-left of the symbol's bounding region in
LTspice convention). The IR pin name keys here are the same strings the
SPICE parser emits in :class:`Component.pins`.

All registered symbols are verified against the real LTspice ``.asy`` files
via the audit tests in ``tests/unit/test_symbols.py``. Pin offsets are also
asserted to be multiples of ``LTSPICE_GRID`` at module load — see
:func:`_assert_pin_offsets_grid_aligned`. This guarantees IR invariant 7
(pin absolute positions on grid) by construction once invariant 5
(component on grid) holds.
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


# Verified — the audit test in tests/unit/test_symbols.py compares these
# offsets against the real .asy files at runtime when LTspice is installed.
_RES = SymbolGeometry(
    name="res",
    pins={"1": (16, 16), "2": (16, 96)},
    bbox=(0, 16, 32, 96),
)

_IND = SymbolGeometry(
    name="ind",
    pins={"1": (16, 16), "2": (16, 96)},
    bbox=(0, 16, 32, 96),
)

_CAP = SymbolGeometry(
    name="cap",
    pins={"1": (16, 0), "2": (16, 64)},
    bbox=(0, 0, 32, 64),
)

_POLCAP = SymbolGeometry(
    name="polcap",
    pins={"1": (16, 0), "2": (16, 64)},
    bbox=(-16, 0, 48, 100),
)

_DIODE = SymbolGeometry(
    name="diode",
    pins={"A": (16, 0), "K": (16, 64)},
    bbox=(0, 0, 32, 64),
)

_NPN = SymbolGeometry(
    name="npn",
    pins={"C": (64, 0), "B": (0, 48), "E": (64, 96)},
    bbox=(0, 0, 64, 96),
)

_PNP = SymbolGeometry(
    name="pnp",
    pins={"C": (64, 0), "B": (0, 48), "E": (64, 96)},
    bbox=(0, 0, 64, 96),
)

_VOLTAGE = SymbolGeometry(
    name="voltage",
    pins={"+": (0, 16), "-": (0, 96)},
    bbox=(-32, 16, 32, 96),
)

_CURRENT = SymbolGeometry(
    name="current",
    pins={"+": (0, 0), "-": (0, 80)},
    bbox=(-32, 0, 32, 80),
)

_BV = SymbolGeometry(
    name="bv",
    pins={"+": (0, 16), "-": (0, 96)},
    bbox=(-32, 16, 32, 96),
)

_E = SymbolGeometry(
    name="e",
    pins={"+": (0, 16), "-": (0, 96), "P": (-48, 32), "N": (-48, 80)},
    bbox=(-48, 16, 32, 96),
)


# Verified against the real LTspice .asy library.
_NMOS = SymbolGeometry(
    name="nmos",
    pins={"D": (48, 0), "G": (0, 80), "S": (48, 96)},
    bbox=(0, 0, 48, 96),
)

_NMOS4 = SymbolGeometry(
    name="nmos4",
    pins={"D": (48, 0), "G": (0, 80), "S": (48, 96), "B": (48, 48)},
    bbox=(0, 0, 48, 96),
)

_PMOS = SymbolGeometry(
    name="pmos",
    pins={"D": (48, 0), "G": (0, 80), "S": (48, 96)},
    bbox=(0, 0, 48, 96),
)

_PMOS4 = SymbolGeometry(
    name="pmos4",
    pins={"D": (48, 0), "G": (0, 80), "S": (48, 96), "B": (48, 48)},
    bbox=(0, 0, 48, 96),
)

_OPAMP = SymbolGeometry(
    name="opamp",
    pins={"invin": (-32, 48), "noninvin": (-32, 80), "out": (32, 64)},
    bbox=(-32, 32, 32, 96),
)

_OPAMP2 = SymbolGeometry(
    name="opamp2",
    pins={
        "In+": (-32, 80),
        "In-": (-32, 48),
        "V+": (0, 32),
        "V-": (0, 96),
        "OUT": (32, 64),
    },
    bbox=(-32, 32, 32, 96),
)


UNVERIFIED_SYMBOLS: frozenset[str] = frozenset()

_REGISTRY: dict[str, SymbolGeometry] = {
    g.name: g
    for g in [
        _RES,
        _IND,
        _CAP,
        _POLCAP,
        _DIODE,
        _NPN,
        _PNP,
        _VOLTAGE,
        _CURRENT,
        _BV,
        _E,
        _NMOS,
        _NMOS4,
        _PMOS,
        _PMOS4,
        _OPAMP,
        _OPAMP2,
    ]
}


def _assert_pin_offsets_grid_aligned() -> None:
    """Module-load invariant: every registered pin offset is on the LTspice grid.

    This is invariant 7 from docs/specs/ir.md, enforced by construction so that
    a new symbol record with off-grid pins fails import rather than at runtime
    in the placer or emitter.
    """
    from wirewright.ir.validate import LTSPICE_GRID

    for geo in _REGISTRY.values():
        for pin_name, (dx, dy) in geo.pins.items():
            if dx % LTSPICE_GRID != 0 or dy % LTSPICE_GRID != 0:
                raise AssertionError(
                    f"Symbol {geo.name!r} pin {pin_name!r} offset ({dx}, {dy}) "
                    f"not aligned to LTspice grid ({LTSPICE_GRID})"
                )


_assert_pin_offsets_grid_aligned()


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
            return (-dx, dy)
        case "M90":
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
