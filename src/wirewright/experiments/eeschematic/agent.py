"""VCoT placement agent for EEschematic-style LLM-driven placement.

Loop (one iteration):

1. If first iteration, no image. Otherwise render the current state.
2. Call GPT-5 vision with the netlist, current JSON, and current image.
3. Parse JSON from the response (tolerate code fences).
4. Translate JSON → placed IR (by ref, not by typeName).
5. Run wirewright's existing router + rails on the placement.
6. Validate. If valid, remember as best-so-far. If model emitted DONE,
   return.
7. Repeat up to ``max_iters``.

Per-fixture spend is capped by ``budget_usd`` (default $20) and
``max_iters``. Both are soft stops that raise ``PlacerEngineError``.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from wirewright.experiments.eeschematic.openai_client import vision_call
from wirewright.experiments.eeschematic.prompts import (
    PLACE_SYSTEM,
    PLACE_USER_CRITIQUE,
    PLACE_USER_INITIAL,
    format_net_list,
    format_ref_symbol_list,
)
from wirewright.experiments.eeschematic.render import render_schematic_png
from wirewright.experiments.eeschematic.translator import eeschematic_json_to_ir
from wirewright.experiments.eeschematic.wiring import wire_placed_schematic
from wirewright.ir.model import Schematic
from wirewright.ir.validate import validate_placed
from wirewright.placers.base import PlacerEngineError
from wirewright.routing.rails import RailMode

logger = logging.getLogger(__name__)


_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")
_CODE_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.MULTILINE)


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of ``text``, tolerating code fences."""
    # Try fenced block first.
    for match in _CODE_FENCE.finditer(text):
        payload = match.group(1).strip()
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    # Fall back to the first {...} span.
    m = _JSON_BLOCK.search(text)
    if m:
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise ValueError(f"could not parse JSON block: {e!s}") from e
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("no JSON object found in response")


def _netlist_text(sch: Schematic) -> str:
    """Pin-safe netlist re-emission for the prompt.

    The parser doesn't retain original SPICE text and ``sorted(pins)``
    gives the wrong order for multi-pin devices (e.g. ``npn`` would come
    out B/C/E, not SPICE's C/B/E). Emit explicit ``pin=net`` pairs so
    the model can't be misled by positional ambiguity. Format:

        <ref>:<symbol>  <pin>=<net>  <pin>=<net>  ...  [value]
    """
    lines = []
    for c in sch.components:
        pairs = "  ".join(f"{pn}={nn}" for pn, nn in c.pins.items())
        extra = f"  [{c.value}]" if c.value else ""
        lines.append(f"{c.ref}:{c.symbol}  {pairs}{extra}")
    return "\n".join(lines)


def place(
    sch: Schematic,
    *,
    max_iters: int = 3,
    budget_usd: float = 20.0,
    rails: RailMode = "clustered",
    model: str = "gpt-5",
    workdir: Path | None = None,
) -> Schematic:
    # Under advisor-forced iter-0 critique rule we need at least 2
    # iterations: iter 0 proposes, iter 1 critiques the render. Below
    # that we can't run VCoT at all.
    if max_iters < 2:
        max_iters = 2
    """Run the VCoT placement loop and return a placed Schematic.

    ``workdir`` holds per-iteration PNG renders and ``calls.jsonl``.
    When ``None``, uses a sibling temp directory of the system.
    """
    if not sch.components:
        return sch

    # Per-fixture workdir keeps calls.jsonl, response text, and iter
    # PNGs from different runs separated. Default directory uses the
    # schematic's title or a stable hash so repeat runs land cleanly.
    if workdir is None:
        stem = sch.title or f"anon-{abs(hash(tuple(c.ref for c in sch.components))) % 10_000}"
        workdir = Path("_cmp") / stem
    else:
        workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    # Fresh calls.jsonl per run — otherwise cost accounting mixes stale
    # entries from previous invocations.
    log_path = workdir / "calls.jsonl"
    if log_path.exists():
        log_path.unlink()

    netlist = _netlist_text(sch)
    ref_syms = format_ref_symbol_list(sch)
    net_list = format_net_list(sch)

    accumulated_cost = 0.0
    current_json: dict[str, Any] | None = None
    current_placed: Schematic | None = None
    best_valid: Schematic | None = None
    last_errors: list[str] = []

    for i in range(max_iters):
        if i == 0 or current_placed is None:
            user_text = PLACE_USER_INITIAL.format(
                netlist=netlist,
                ref_symbol_list=ref_syms,
                net_list=net_list,
            )
            image_paths: list[Path] = []
        else:
            img = workdir / f"iter_{i:02d}.png"
            render_schematic_png(current_placed, img)
            critique = PLACE_USER_CRITIQUE.format(
                netlist=netlist,
                current_json=json.dumps(current_json, indent=2),
            )
            if last_errors:
                # Feed structural findings as text — model can't be
                # relied on to read pixels for shorts; naming them
                # explicitly steers the next placement.
                critique += "\n\nValidation findings from your last placement:\n"
                critique += "\n".join(f"  - {e}" for e in last_errors)
                critique += (
                    "\n\nAddress these before emitting DONE. If placement "
                    "looks good and no findings remain, append DONE on its "
                    "own line."
                )
            user_text = critique
            image_paths = [img]

        result = vision_call(
            system=PLACE_SYSTEM,
            user_text=user_text,
            image_paths=image_paths,
            model=model,
            log_path=log_path,
        )
        accumulated_cost += result.cost_usd
        logger.info(
            "iter %d: $%.4f (cum $%.4f), finish=%s, chars=%d",
            i,
            result.cost_usd,
            accumulated_cost,
            result.finish_reason,
            len(result.text),
        )
        # Save full response text alongside the iteration PNG so the
        # user (and advisor) can see what the model actually emitted.
        (workdir / f"iter_{i:02d}.response.txt").write_text(result.text)
        if accumulated_cost > budget_usd:
            raise PlacerEngineError(
                f"EEschematic budget ${budget_usd:.2f} exceeded "
                f"(spent ${accumulated_cost:.4f})"
            )

        try:
            parsed = _extract_json(result.text)
        except ValueError as e:
            logger.warning("iter %d: json parse failed: %s", i, e)
            last_errors = [f"JSON parse failed: {e!s}"]
            continue

        current_json = parsed
        last_errors = []
        try:
            placed = eeschematic_json_to_ir(sch, parsed)
            wired = wire_placed_schematic(placed, rails=rails)
            validate_placed(wired)
        except Exception as e:
            logger.warning("iter %d: translate/wire/validate failed: %s", i, e)
            last_errors = [f"{type(e).__name__}: {e!s}"]
            current_placed = (
                eeschematic_json_to_ir(sch, parsed) if parsed else current_placed
            )
            continue

        current_placed = wired
        best_valid = wired
        # Honor DONE only after iter 0 — the model has not yet seen a
        # render of its own placement on iter 0, so its claim of
        # "nothing to improve" is not grounded. Force at least one
        # Visual Chain-of-Thought round.
        if i > 0 and re.search(r"\bDONE\b", result.text):
            logger.info("iter %d: DONE sigil, returning", i)
            break

    if best_valid is None:
        raise PlacerEngineError(
            f"EEschematic: no valid placement in {max_iters} iterations "
            f"(spent ${accumulated_cost:.4f})"
        )
    return best_valid
