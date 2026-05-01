"""Runtime configuration for wirewright.

Currently stub-level. Phase 1+ will add an actual config file (TOML in
``~/.config/wirewright/`` or per-project ``wirewright.toml``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    """Runtime config. v0.0.1: defaults only."""

    default_placer: str = "naive"
    grid_unit: int = 16
