"""The Placer abstract base class. See docs/specs/placer-interface.md."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from wirewright.ir.model import Schematic

if TYPE_CHECKING:
    from wirewright.routing.rails import RailMode


class PlacerError(Exception):
    """Raised when a placer cannot complete placement (bad input or constraints)."""


class PlacerEngineError(PlacerError):
    """Raised when an underlying placement engine (Node bridge, pyhola) fails."""


class Placer(ABC):
    """Abstract base class for placement back ends.

    See :doc:`docs/specs/placer-interface.md` for the full contract.
    Implementations must be pure (no mutation of the input), total (place
    every component), validating (output passes ``ir.validate.validate_placed``),
    deterministic (same input + hints = same output), and grid-snapped.

    All placers accept a ``rails`` constructor option selecting the
    power/ground rendering mode. See :data:`wirewright.routing.rails.RailMode`.
    """

    name: str

    def __init__(self, rails: RailMode = "clustered") -> None:
        self.rails = rails

    @abstractmethod
    def place(
        self,
        schematic: Schematic,
        hints: dict[str, Any] | None = None,
    ) -> Schematic:
        """Return a new Schematic with placement and routing populated.

        Hints are placer-specific. All placers should silently ignore unknown
        hints. Common hints all placers should at least understand:

        - ``direction``: ``'LR'``, ``'RL'``, ``'TB'``, ``'BT'`` (signal flow).
        - ``aspect_ratio``: float (target width/height).
        - ``pinned``: ``dict[ref, (x, y, orientation)]`` to pin specific
          components to fixed positions before laying out the rest.
        """
        ...
