"""HOLA (Human-like Orthogonal Layout) placer adapter.

PHASE 4. Currently a stub that raises with a helpful message.

The plan: convert IR to HOLA's input format with port constraints via pyhola,
call HOLA, snap to the LTspice grid, and return a populated Schematic.

HOLA produces more compact, more symmetric layouts than ELK Layered. It is
the preferred back end for analog circuits with feedback loops and balanced
sections (differential pairs, current mirrors, ladder filters). See
``docs/adr/0004-elk-and-hola-as-baselines.md`` for the rationale.

Reference:
    Kieffer, Dwyer, Marriott, Wybrow.
    "HOLA: Human-like Orthogonal Network Layout."
    IEEE TVCG 22(1), 2016.
"""

from __future__ import annotations

from typing import Any

from wirewright.ir.model import Schematic
from wirewright.placers.base import Placer


class HolaPlacer(Placer):
    """Stress-majorization with port constraints, producing human-style layouts."""

    name = "hola"

    def place(
        self,
        schematic: Schematic,
        hints: dict[str, Any] | None = None,
    ) -> Schematic:
        raise NotImplementedError(
            "HolaPlacer lands in Phase 4. See docs/PLAN.md.\n"
            "Requires building pyhola against adaptagrams; see docs/build-hola.md "
            "(coming in Phase 4). Use --placer naive in the meantime."
        )
