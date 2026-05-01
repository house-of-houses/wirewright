"""Placement back ends. Every placer implements :class:`Placer`."""

from wirewright.placers.base import Placer, PlacerEngineError, PlacerError
from wirewright.placers.grid_naive import NaivePlacer

__all__ = [
    "NaivePlacer",
    "Placer",
    "PlacerEngineError",
    "PlacerError",
    "get_placer",
    "registry",
]


def get_placer(name: str) -> Placer:
    """Look up a placer by short name (the ``--placer`` CLI argument)."""
    if name not in registry:
        available = sorted(registry)
        raise KeyError(f"Unknown placer {name!r}. Available: {available}")
    return registry[name]()


# Lazy-import HOLA so a missing hola-graph dep doesn't break the CLI for
# users who only need naive placement.
from wirewright.placers.hola import HolaPlacer  # noqa: E402

registry: dict[str, type[Placer]] = {
    "naive": NaivePlacer,
    "hola": HolaPlacer,
}
