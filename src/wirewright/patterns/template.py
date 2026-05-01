"""YAML pattern template loader.

See ``docs/specs/pattern-library.md`` for the grammar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]

from wirewright.ir.model import Orientation
from wirewright.ir.validate import LTSPICE_GRID

_VALID_ORIENTATIONS: frozenset[str] = frozenset(
    {"R0", "R90", "R180", "R270", "M0", "M90", "M180", "M270"}
)


class TemplateError(Exception):
    """Raised when a YAML template cannot be parsed."""


@dataclass(frozen=True)
class ComponentSpec:
    role: str
    symbol: str
    spice_prefix: str | None = None
    value_pattern: str | None = None
    spice_model_pattern: str | None = None


@dataclass(frozen=True)
class TopologyConstraint:
    """One topology constraint: ``==`` (same net), ``!=`` (different net), or GND."""

    kind: Literal["same", "diff", "ground"]
    a: tuple[str, str]
    b: tuple[str, str] | None = None


@dataclass(frozen=True)
class PlacementHint:
    role: str
    dx: int
    dy: int
    orientation: Orientation = "R0"


@dataclass
class Template:
    name: str
    version: int
    description: str
    priority: int
    components: list[ComponentSpec]
    topology: list[TopologyConstraint]
    placement: list[PlacementHint] = field(default_factory=list)


def _parse_topology_line(line: str) -> TopologyConstraint:
    line = line.strip()
    if "==" in line:
        lhs, rhs = (s.strip() for s in line.split("==", 1))
        if rhs.upper() in ("GND", "0"):
            role, pin = lhs.split(".", 1)
            return TopologyConstraint(kind="ground", a=(role.strip(), pin.strip()))
        a_role, a_pin = lhs.split(".", 1)
        b_role, b_pin = rhs.split(".", 1)
        return TopologyConstraint(
            kind="same",
            a=(a_role.strip(), a_pin.strip()),
            b=(b_role.strip(), b_pin.strip()),
        )
    if "!=" in line:
        lhs, rhs = (s.strip() for s in line.split("!=", 1))
        a_role, a_pin = lhs.split(".", 1)
        b_role, b_pin = rhs.split(".", 1)
        return TopologyConstraint(
            kind="diff",
            a=(a_role.strip(), a_pin.strip()),
            b=(b_role.strip(), b_pin.strip()),
        )
    raise TemplateError(f"unrecognized topology constraint: {line!r}")


def load_template(path: str | Path) -> Template:
    """Parse a YAML template file."""
    p = Path(path)
    raw = yaml.safe_load(p.read_text())
    if not isinstance(raw, dict):
        raise TemplateError(f"{p}: top-level must be a mapping")
    try:
        components = [ComponentSpec(**c) for c in raw["match"]["components"]]
        topology = [_parse_topology_line(line) for line in raw["match"]["topology"]]
    except (KeyError, TypeError) as e:
        raise TemplateError(f"{p}: malformed match block: {e}") from e

    if len(components) < 2:
        raise TemplateError(
            f"{p}: single-component templates not supported in v0.1; VF2 needs ≥2 roles"
        )

    placement: list[PlacementHint] = []
    for role, hint in (raw.get("placement") or {}).items():
        try:
            dx = int(hint["dx"])
            dy = int(hint["dy"])
        except (KeyError, TypeError) as e:
            raise TemplateError(f"{p}: malformed placement for role {role!r}: {e}") from e
        if dx % LTSPICE_GRID != 0 or dy % LTSPICE_GRID != 0:
            raise TemplateError(
                f"{p}: placement {role!r} (dx={dx}, dy={dy}) "
                f"not aligned to LTspice grid (multiple of {LTSPICE_GRID})"
            )
        orient = hint.get("orientation", "R0")
        if orient not in _VALID_ORIENTATIONS:
            raise TemplateError(f"{p}: placement {role!r} has invalid orientation {orient!r}")
        placement.append(PlacementHint(role=role, dx=dx, dy=dy, orientation=orient))

    return Template(
        name=raw["name"],
        version=int(raw.get("version", 1)),
        description=raw.get("description", ""),
        priority=int(raw.get("priority", 100)),
        components=components,
        topology=topology,
        placement=placement,
    )


def load_default_library() -> list[Template]:
    """Load every YAML template shipped under ``wirewright/patterns/library/``."""
    here = Path(__file__).resolve().parent / "library"
    return [load_template(p) for p in sorted(here.glob("*.yaml"))]
