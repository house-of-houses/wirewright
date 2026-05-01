"""IR dataclasses. See docs/specs/ir.md for the spec."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Orientation = Literal[
    "R0",
    "R90",
    "R180",
    "R270",
    "M0",
    "M90",
    "M180",
    "M270",
]
"""LTspice symbol orientations: four rotations and four mirrored rotations."""

Side = Literal["N", "E", "S", "W"]


@dataclass(frozen=True)
class Pin:
    """A pin on a component symbol.

    The ``side`` is an optional hint to the placer about which side of the
    symbol the pin sits on. The actual pin offsets in canvas coordinates live
    in ``wirewright.symbols``, not here.
    """

    name: str
    side: Side | None = None


@dataclass
class Component:
    """A placed (or to-be-placed) circuit element.

    Coordinates are integers in LTspice grid units (16 mils per unit).
    Coordinates are ``None`` until a placer has run.
    """

    ref: str
    """Reference designator like 'R1', 'Q3', 'U2'."""

    symbol: str
    """LTspice symbol library name without ``.asy``: 'res', 'npn', 'opamp2'."""

    value: str | None = None
    """Human label like '10k', '1n', 'LM358'."""

    pins: dict[str, str] = field(default_factory=dict)
    """Pin name to net name: {'1': 'vin', '2': 'n001'} for a resistor."""

    spice_model: str | None = None
    """The SPICE model name when relevant (BJTs, MOSFETs, diodes)."""

    spice_prefix: str | None = None
    """The SPICE element prefix letter ('R', 'C', 'Q', 'M', 'D', ...)."""

    # Populated by the placer. None means unplaced.
    x: int | None = None
    y: int | None = None
    orientation: Orientation = "R0"

    @property
    def is_placed(self) -> bool:
        return self.x is not None and self.y is not None


@dataclass
class Net:
    """An electrical node in the circuit."""

    name: str
    is_power: bool = False
    """Routed as a global rail rather than ordinary edges."""

    is_ground: bool = False
    """Net '0' (or any net so marked) is ground. Routed via FLAG '0' symbols."""


@dataclass(frozen=True)
class Wire:
    """An axis-aligned wire segment between two grid points."""

    x1: int
    y1: int
    x2: int
    y2: int

    def __post_init__(self) -> None:
        if self.x1 != self.x2 and self.y1 != self.y2:
            raise ValueError(
                f"Wire {self} is not axis-aligned. Diagonal wires are not allowed in the IR."
            )


@dataclass(frozen=True)
class Flag:
    """A net label placed at a specific point on the canvas.

    If ``net == '0'``, LTspice renders this as a GND symbol. Otherwise it
    renders as an IO label with text ``net``.
    """

    x: int
    y: int
    net: str


@dataclass
class Schematic:
    """The complete IR for one schematic.

    Parsing produces a ``Schematic`` with ``components`` and ``nets``
    populated and ``components[*].x/y/orientation`` left as None.

    Placement returns a ``Schematic`` with everything populated, including
    ``wires`` and ``flags``.
    """

    components: list[Component] = field(default_factory=list)
    nets: list[Net] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    directives: list[str] = field(default_factory=list)
    """Raw SPICE directives like '.tran 1m', '.ac dec 100 1 1Meg'."""

    title: str | None = None

    def component_by_ref(self, ref: str) -> Component:
        """Lookup helper. Raises KeyError if not found."""
        for c in self.components:
            if c.ref == ref:
                return c
        raise KeyError(f"No component with ref {ref!r}")

    def net_by_name(self, name: str) -> Net:
        for n in self.nets:
            if n.name == name:
                return n
        raise KeyError(f"No net with name {name!r}")

    @property
    def is_placed(self) -> bool:
        """True iff every component has coordinates."""
        return all(c.is_placed for c in self.components)
