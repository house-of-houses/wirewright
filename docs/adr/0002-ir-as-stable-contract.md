# ADR 0002: IR as the stable internal contract

**Status**: Accepted

**Date**: 2026-05-01

## Context

We have at least three boundaries that need a shared data shape: parser-to-placer, placer-to-emitter, and (eventually) pattern-matcher-to-placer. Without a defined IR, every pair of modules invents its own dict shape and changing anything ripples everywhere.

## Decision

Define a single Internal Representation (`src/wirewright/ir/model.py`) using Python dataclasses with type hints. Every module that crosses a boundary speaks IR. The IR is specified in `docs/specs/ir.md` and changes to it require an ADR superseding this one or an explicit spec update with migration notes.

## Rationale

Dataclasses are explicit, introspectable, easy to test, easy to serialize for debugging, and play well with mypy.

A single IR means the Phase 5 pattern matcher can be added without touching the parser or the emitter. New placers plug in by mapping IR-to-placer-input and placer-output-to-IR. A new input format (KiCad netlist? Qucs?) plugs in by mapping input-to-IR.

The alternative (every module passing dicts around) optimizes for short-term flexibility at the cost of long-term cohesion. We accept the up-front design cost.

## Consequences

- All other modules import from `wirewright.ir`. There must not be circular dependencies into `ir/`.
- Coordinates in IR are integers in LTspice grid units. No other unit system leaks in.
- IR changes are breaking changes by default. We will use Pydantic v2 for the IR types so we can version and validate explicitly if needed.
- `ir/validate.py` enforces invariants: every component pin's net exists, every wire endpoint sits on the LTspice grid, no two components overlap (post-placement), every power/ground net is marked as such.
