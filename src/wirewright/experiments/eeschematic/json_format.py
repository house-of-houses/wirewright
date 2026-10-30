"""EEschematic JSON schema — typed interface to the upstream format.

Mirrors the schema emitted by https://github.com/eelab-dev/EEschematic
(MIT License, Copyright (c) 2025 EElab.dev). Kept read-close to the
upstream prompts so Claude-produced JSON matches what their prompts
instruct the model to emit.

Upstream coordinate convention (confirmed by ``place_prompt.txt`` and
``node_prompt.txt``):

- ``x`` and ``y`` are small integers on a grid in ``[-60, 60]``.
- Positive x = right; positive y = up (grid-math, not screen).
- Rotation is a *string* enum: ``"0"``, ``"90"``, ``"180"``, ``"270"``.
- Flip is a string enum: ``"none"``, ``"horizontal"``, ``"vertical"``.

Translation to wirewright IR happens in :mod:`.translator`; this module
defines only the wire-format types.

Prompt roles (from ``netlist_to_schema/*.txt`` in the upstream repo):

Placement loop
    - ``place_prompt.txt``   — netlist → componentInstances JSON
    - ``check_prompt.txt``   — netlist + JSON → corrected JSON
    - ``modify_prompt.txt``  — netlist + JSON + screenshot → optimised
      JSON (this is the Visual Chain-of-Thought step)

Wiring loop
    - ``node_prompt.txt``       — JSON → per-pin absolute positions
    - ``connect_prompt.txt``    — netlist + JSON + nodes → suggested
      start/end wire pairs
    - ``connecting_prompt.txt`` — suggestion → ``startlocation`` /
      ``endlocation`` arrays
    - ``wire_correction.txt`` + ``wire_correction_action.txt`` —
      post-wiring repair pass

Upstream MIT license text lives at
``src/wirewright/experiments/eeschematic/LICENSE_EESCHEMATIC``.
"""

from __future__ import annotations

from typing import Literal, TypedDict

#: EEschematic ``typeName`` values seen in the upstream prompts and
#: notebooks. Not exhaustive — the model occasionally emits variants
#: (e.g. ``"nmos"`` instead of ``"nFET"``) which the translator must
#: tolerate.
TypeName = Literal[
    "VDD",
    "GND",
    "nFET",
    "pFET",
    "resistor",
    "capacitor",
    "vdc",
    "idc",
    "port",
]

Rotation = Literal["0", "90", "180", "270"]
Flip = Literal["none", "horizontal", "vertical"]


class Origin(TypedDict):
    """2D coordinate on EEschematic's ``[-60, 60]`` grid.

    Positive x extends right, positive y extends up (math convention).
    """

    x: int
    y: int


class ComponentInstance(TypedDict, total=False):
    """One placed component in the EEschematic JSON schema.

    ``value`` is absent for VDD and GND placeholders in the upstream
    examples, so this TypedDict is ``total=False`` and the translator
    treats a missing ``value`` as empty string.
    """

    typeName: TypeName | str
    name: str
    value: str
    origin: Origin
    rotation: Rotation | str
    flip: Flip | str


class Schema(TypedDict):
    """Top-level EEschematic JSON structure returned by placement prompts."""

    componentInstances: list[ComponentInstance]


#: One pin's absolute position, keyed by pin letter (``D``, ``G``,
#: ``S``, ``B`` for FETs). Emitted by ``node_prompt.txt``.
PinPosition = tuple[int, int]  # (x, y)


class NodeLocation(TypedDict):
    """``node_prompt`` output for one component: pin letter → (x, y)."""

    name: str  # e.g. "M1"
    pins: dict[str, PinPosition]  # {"D": (1, 6), "G": (-4, 1), ...}


#: Wire endpoint as emitted by ``connecting_prompt.txt``:
#: ``(node_name, x, y)``.
WireEndpoint = tuple[str, int, int]


class WireList(TypedDict):
    """Output of ``connecting_prompt.txt``: parallel start/end arrays.

    ``startlocation[i]`` connects to ``endlocation[i]``.
    """

    startlocation: list[WireEndpoint]
    endlocation: list[WireEndpoint]
