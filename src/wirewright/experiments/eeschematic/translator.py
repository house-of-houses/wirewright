"""Translate EEschematic JSON placement onto a wirewright IR.

Advisor-driven design (2026-10-30): the translator does NOT construct
``Component`` objects from the model's output. It takes the parsed-but-
unplaced input :class:`Schematic`, deep-copies it, and sets only
``x`` / ``y`` / ``orientation`` on components whose ``ref`` matches a
``componentInstance.name``. The input schematic remains the source of
truth for component identity, pins, nets, and symbol library.

Consequences:

- Component set is preserved by construction (T1 test holds).
- EEschematic's ``typeName`` enum is advisory — the prompt lists refs
  with their wirewright symbol names (``R1:res Q3:npn ...``) and we
  ignore whatever typeName the model echoes back.
- VDD / GND instances in the JSON are ignored. Power and ground are
  handled by :func:`wirewright.routing.rails.emit_power_ground_rails`.
- Missing refs leave the corresponding component unplaced — downstream
  :func:`validate_placed` catches it.

Coordinate conventions:

- Scale: ``1 EEschematic unit = 16 IR units`` (one LTspice grid cell).
- Y axis: EEschematic ``y`` positive up, IR positive down → negate.
- Rotation: ``"0" / "90" / "180" / "270"`` (string or int tolerated).
- Flip: ``"none"`` → base, ``"horizontal"`` → ``M{rot}``,
  ``"vertical"`` → ``M{(180+rot)%360}`` (vertical flip = M180 at R0,
  equivalent to M-family rotated).
"""

from __future__ import annotations

import copy
from typing import Any

from wirewright.ir.model import Orientation, Schematic

EE_UNIT_IN_IR = 16  # one LTspice grid cell per EEschematic unit


def _normalize_rotation(raw: Any) -> int:
    """Return rotation as int in {0, 90, 180, 270}; tolerate str or int."""
    try:
        n = int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        n = 0
    n %= 360
    if n not in (0, 90, 180, 270):
        # Snap to nearest multiple of 90 — prompt is sloppy enough that
        # we see 45° occasionally.
        n = min((0, 90, 180, 270), key=lambda c: min(abs(n - c), 360 - abs(n - c)))
    return n


def _flip_rotation_to_orientation(flip: Any, rotation: Any) -> Orientation:
    """Map (flip, rotation) → LTspice orientation name."""
    rot = _normalize_rotation(rotation)
    flip_s = str(flip or "none").lower()
    if flip_s in ("none", "", "false"):
        return f"R{rot}"  # type: ignore[return-value]
    if flip_s == "vertical":
        rot = (rot + 180) % 360
    # both "horizontal" and "vertical" land here with the right rot
    return f"M{rot}"  # type: ignore[return-value]


def _is_rail_placeholder(name: str, typename: str) -> bool:
    """VDD and GND componentInstances are rail metadata, not components."""
    if typename in ("VDD", "GND"):
        return True
    n = name.upper()
    return n == "VDD" or n.startswith("GND") or n == "VSS" or n == "VCC"


def eeschematic_json_to_ir(unplaced: Schematic, data: dict[str, Any]) -> Schematic:
    """Apply EEschematic placement JSON onto a copy of ``unplaced``.

    Components whose ``ref`` is absent from ``data["componentInstances"]``
    stay unplaced; downstream validation surfaces them.

    Instances whose ``name`` matches no component are silently ignored
    (likely VDD/GND placeholders handled by rails).
    """
    out = copy.deepcopy(unplaced)
    by_ref = {c.ref: c for c in out.components}

    instances = data.get("componentInstances") or []
    for inst in instances:
        if not isinstance(inst, dict):
            continue
        name = str(inst.get("name") or "")
        typename = str(inst.get("typeName") or "")
        if not name or _is_rail_placeholder(name, typename):
            continue
        comp = by_ref.get(name)
        if comp is None:
            continue

        origin = inst.get("origin") or {}
        try:
            x_ee = int(origin.get("x", 0))
            y_ee = int(origin.get("y", 0))
        except (TypeError, ValueError):
            continue  # bad origin — leave unplaced

        comp.x = x_ee * EE_UNIT_IN_IR
        comp.y = -y_ee * EE_UNIT_IN_IR  # Y flip EE up → IR down
        comp.orientation = _flip_rotation_to_orientation(
            inst.get("flip"), inst.get("rotation")
        )

    return out
