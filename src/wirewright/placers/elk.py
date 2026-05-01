"""ELK (Eclipse Layout Kernel) placer adapter.

PHASE 3. Currently a stub that raises with a helpful message.

The plan: convert IR to ELK's JSON graph format with port constraints, call
the Node.js bridge in ``tools/elk-bridge/``, parse the result back, snap to
the LTspice grid, and return a populated Schematic.

Power and ground nets are removed before sending to ELK and re-added as
global rails after layout.
"""

from __future__ import annotations

from typing import Any

from wirewright.ir.model import Schematic
from wirewright.placers.base import Placer


class ElkPlacer(Placer):
    """Layered Sugiyama-style placement via Eclipse Layout Kernel."""

    name = "elk"

    def place(
        self,
        schematic: Schematic,
        hints: dict[str, Any] | None = None,
    ) -> Schematic:
        raise NotImplementedError(
            "ElkPlacer lands in Phase 3. See docs/PLAN.md.\n"
            "Use --placer naive in the meantime, or --placer hola once Phase 4 ships."
        )
