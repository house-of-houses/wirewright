"""EEschematicPlacer — MLLM-based placer (side experiment).

See ``docs/plans/eeschematic-experiment.md``.

This placer is non-deterministic by contract (``deterministic = False``);
its ``TestAnyPlacer`` determinism assertion is skipped per the amended
``docs/specs/placer-interface.md``.

The constructor fails fast when ``OPENAI_API_KEY`` is unset, so
``wirewright render --placer eeschematic`` errors cheaply without a key
and nothing in CI can silently fire a billable call.
"""

from __future__ import annotations

import os
from typing import Any

from wirewright.ir.model import Schematic
from wirewright.placers.base import Placer
from wirewright.routing.rails import RailMode


class EEschematicPlacer(Placer):
    """GPT-5-vision-driven placer. Non-deterministic by contract."""

    name = "eeschematic"
    deterministic = False

    def __init__(self, rails: RailMode = "clustered") -> None:
        super().__init__(rails=rails)
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError(
                "EEschematicPlacer requires OPENAI_API_KEY. "
                "This placer is an experimental side branch — see "
                "docs/plans/eeschematic-experiment.md."
            )

    def place(
        self,
        schematic: Schematic,
        hints: dict[str, Any] | None = None,
    ) -> Schematic:
        # Deferred import — matplotlib / openai live in the experiments
        # extra and must not be hard dependencies of the placer registry.
        from wirewright.experiments.eeschematic.agent import place as _place

        del hints  # not used in v0.3-experiment
        return _place(schematic, rails=self.rails)
