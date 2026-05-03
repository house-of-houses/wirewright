"""Auto-fallback placer: try HOLA first, fall back to naive on engine errors.

This is the recommended default for v0.2: HOLA gives the best output on
most circuits, but 3 of the 21 canonical TB-303 fixtures abort inside
HOLA's C++ (`faces.cpp::identifyExternalFace`). Auto turns that abort
into a silent fallback so the user always gets a renderable `.asc`.
"""

from __future__ import annotations

from typing import Any

from wirewright.ir.model import Schematic
from wirewright.placers.base import Placer, PlacerEngineError
from wirewright.placers.grid_naive import NaivePlacer
from wirewright.routing.rails import RailMode


class AutoPlacer(Placer):
    """Try HOLA first; fall back to NaivePlacer on PlacerEngineError."""

    name = "auto"

    def __init__(self, rails: RailMode = "clustered") -> None:
        self.rails = rails

    def place(
        self,
        schematic: Schematic,
        hints: dict[str, Any] | None = None,
    ) -> Schematic:
        from wirewright.placers.hola import HolaPlacer

        try:
            return HolaPlacer(rails=self.rails).place(schematic, hints=hints)
        except PlacerEngineError:
            return NaivePlacer(rails=self.rails).place(schematic, hints=hints)
