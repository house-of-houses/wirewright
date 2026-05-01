"""LTspice .asc file parser. See docs/specs/asc-emitter.md for the inverse.

Round-trip lossy properties (documented; tested in
tests/integration/test_round_trip.py):

- ``Net.is_power`` is reset to False on every parsed net (no ``.asc``
  convention to mark a net as power).
- ``Schematic.nets`` ordering is not preserved across round-trip.
- ``Component.spice_prefix`` for standard prefixes (R/C/L/V/I/D/Q/M) is
  dropped — the emitter only writes ``SYMATTR Prefix`` for non-standard
  prefixes since LTspice infers standard ones from the symbol.
- Free TEXT comments (``;``-prefixed) are dropped (no IR field in v0.1).
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import cast, get_args

from wirewright.ir.model import Component, Flag, Net, Orientation, Schematic, Wire
from wirewright.symbols.builtin import absolute_pin_position, symbol_geometry


class AscParseError(Exception):
    """Raised when a .asc file cannot be parsed."""


_VALID_ORIENTATIONS: frozenset[str] = frozenset(get_args(Orientation))


def parse_asc_file(path: str | Path) -> Schematic:
    """Parse a .asc file into IR with positions populated."""
    return parse_asc_text(Path(path).read_text())


def parse_asc_text(text: str) -> Schematic:
    """Parse .asc text into IR with positions populated."""
    lines = text.splitlines()
    if not lines or not lines[0].startswith("Version "):
        raise AscParseError("missing 'Version N' header on first line")

    components: list[Component] = []
    wires: list[Wire] = []
    flags: list[Flag] = []
    directives: list[str] = []
    current: Component | None = None

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("Version") or line.startswith("SHEET"):
            continue

        tokens = line.split()
        kind = tokens[0]

        if kind == "WIRE":
            if len(tokens) != 5:
                raise AscParseError(f"line {line_no}: malformed WIRE: {line!r}")
            try:
                wire = Wire(int(tokens[1]), int(tokens[2]), int(tokens[3]), int(tokens[4]))
            except ValueError as e:
                raise AscParseError(f"line {line_no}: invalid WIRE: {e}") from e
            wires.append(wire)

        elif kind == "FLAG":
            if len(tokens) != 4:
                raise AscParseError(f"line {line_no}: malformed FLAG: {line!r}")
            flags.append(Flag(int(tokens[1]), int(tokens[2]), tokens[3]))

        elif kind == "SYMBOL":
            if len(tokens) != 5:
                raise AscParseError(f"line {line_no}: malformed SYMBOL: {line!r}")
            symbol, sx, sy, orient = tokens[1], int(tokens[2]), int(tokens[3]), tokens[4]
            if orient not in _VALID_ORIENTATIONS:
                raise AscParseError(f"line {line_no}: unknown orientation {orient!r}")
            current = Component(
                ref="",
                symbol=symbol,
                pins={},
                x=sx,
                y=sy,
                orientation=cast(Orientation, orient),
            )
            components.append(current)

        elif kind == "SYMATTR":
            if current is None:
                raise AscParseError(f"line {line_no}: SYMATTR without preceding SYMBOL")
            if len(tokens) < 3:
                raise AscParseError(f"line {line_no}: malformed SYMATTR: {line!r}")
            key = tokens[1]
            value = " ".join(tokens[2:])
            if key == "InstName":
                current.ref = value
            elif key == "Value":
                current.value = value
            elif key == "SpiceModel":
                current.spice_model = value
            elif key == "Prefix":
                current.spice_prefix = value
            else:
                warnings.warn(
                    f"line {line_no}: unknown SYMATTR key {key!r} dropped",
                    stacklevel=2,
                )

        elif kind == "TEXT":
            if len(tokens) < 6:
                continue
            body = " ".join(tokens[5:])
            if body.startswith("!"):
                directives.append(body[1:])
            # Comments and free text dropped silently (no IR field in v0.1).

        else:
            warnings.warn(
                f"line {line_no}: unknown line type {kind!r} dropped",
                stacklevel=2,
            )

    sch = Schematic(
        components=components,
        nets=[],
        wires=wires,
        flags=flags,
        directives=directives,
    )
    _recover_nets(sch)
    return sch


# ----------------------------------------------------------------------------
# Net recovery via coordinate union-find.
# ----------------------------------------------------------------------------


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[tuple[int, int], tuple[int, int]] = {}

    def find(self, p: tuple[int, int]) -> tuple[int, int]:
        if p not in self._parent:
            self._parent[p] = p
            return p
        root = p
        while self._parent[root] != root:
            root = self._parent[root]
        cur = p
        while self._parent[cur] != root:
            self._parent[cur], cur = root, self._parent[cur]
        return root

    def union(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


_LATTICE_LIMIT = 1024


def _wire_lattice_points(w: Wire) -> list[tuple[int, int]]:
    """All grid-aligned points on the wire segment, including both endpoints."""
    from wirewright.ir.validate import LTSPICE_GRID

    pts: list[tuple[int, int]] = []
    if w.x1 == w.x2:
        ys = sorted([w.y1, w.y2])
        y = ys[0]
        while y <= ys[1]:
            pts.append((w.x1, y))
            y += LTSPICE_GRID
            if len(pts) > _LATTICE_LIMIT:
                raise AscParseError(f"wire {w} spans more than {_LATTICE_LIMIT} grid units")
    else:  # y1 == y2 (axis-aligned by Wire.__post_init__)
        xs = sorted([w.x1, w.x2])
        x = xs[0]
        while x <= xs[1]:
            pts.append((x, w.y1))
            x += LTSPICE_GRID
            if len(pts) > _LATTICE_LIMIT:
                raise AscParseError(f"wire {w} spans more than {_LATTICE_LIMIT} grid units")
    return pts


def _strip_lib_folder(symbol: str) -> str:
    """Strip leading library folder prefix (e.g. 'OpAmps/opamp2' → 'opamp2')."""
    return symbol.rsplit("/", 1)[-1]


def _recover_nets(sch: Schematic) -> None:
    """Populate sch.components[*].pins and sch.nets via coordinate union-find."""
    uf = _UnionFind()

    component_pins: list[tuple[Component, str, tuple[int, int]]] = []
    for c in sch.components:
        if c.x is None or c.y is None:
            continue
        try:
            geo = symbol_geometry(_strip_lib_folder(c.symbol))
        except KeyError as e:
            raise AscParseError(f"Component {c.ref!r} uses unknown symbol {c.symbol!r}") from e
        for pin_name in geo.pins:
            pos = absolute_pin_position(
                (c.x, c.y), _strip_lib_folder(c.symbol), pin_name, c.orientation
            )
            uf.find(pos)
            component_pins.append((c, pin_name, pos))

    for w in sch.wires:
        pts = _wire_lattice_points(w)
        for q in pts[1:]:
            uf.union(pts[0], q)

    for fl in sch.flags:
        uf.find((fl.x, fl.y))

    name_for_root: dict[tuple[int, int], str] = {}
    for fl in sch.flags:
        root = uf.find((fl.x, fl.y))
        existing = name_for_root.get(root)
        if existing is None:
            name_for_root[root] = fl.net
        elif existing != fl.net:
            warnings.warn(
                f"net at {(fl.x, fl.y)} flagged both {existing!r} and {fl.net!r}; "
                f"keeping {existing!r} (first-flag-wins; LTspice-tolerant)",
                stacklevel=2,
            )

    synthetic_counter = 0
    root_to_synthetic: dict[tuple[int, int], str] = {}

    def name_for(pos: tuple[int, int]) -> str:
        nonlocal synthetic_counter
        root = uf.find(pos)
        if root in name_for_root:
            return name_for_root[root]
        if root not in root_to_synthetic:
            synthetic_counter += 1
            root_to_synthetic[root] = f"n{synthetic_counter}"
        return root_to_synthetic[root]

    for c, pin_name, pos in component_pins:
        c.pins[pin_name] = name_for(pos)

    seen: dict[str, Net] = {}
    for c in sch.components:
        for net_name in c.pins.values():
            if net_name in seen:
                continue
            seen[net_name] = Net(name=net_name, is_ground=net_name == "0")
    sch.nets = list(seen.values())
