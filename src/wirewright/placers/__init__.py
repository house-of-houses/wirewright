"""Placement back ends. Every placer implements :class:`Placer`."""

from wirewright.placers.base import Placer, PlacerEngineError, PlacerError
from wirewright.placers.grid_naive import NaivePlacer
from wirewright.routing.rails import RailMode

__all__ = [
    "AutoPlacer",
    "EEschematicPlacer",
    "HolaPlacer",
    "NaivePlacer",
    "Placer",
    "PlacerEngineError",
    "PlacerError",
    "get_placer",
    "registry",
]


def get_placer(name: str, rails: RailMode = "clustered") -> Placer:
    """Look up a placer by short name (the ``--placer`` CLI argument)."""
    if name not in registry:
        available = sorted(registry)
        raise KeyError(f"Unknown placer {name!r}. Available: {available}")
    return registry[name](rails=rails)


# Lazy-import HOLA so a missing hola-graph dep doesn't break the CLI for
# users who only need naive placement.
from wirewright.placers.auto import AutoPlacer  # noqa: E402
from wirewright.placers.eeschematic import EEschematicPlacer  # noqa: E402
from wirewright.placers.hola import HolaPlacer  # noqa: E402

registry: dict[str, type[Placer]] = {
    "naive": NaivePlacer,
    "hola": HolaPlacer,
    "auto": AutoPlacer,
    "eeschematic": EEschematicPlacer,
}
