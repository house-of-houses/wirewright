# ADR 0003: Placer adapter pattern

**Status**: Accepted

**Date**: 2026-05-01

## Context

We want to support multiple placement back ends (naive, ELK, HOLA, eventually others). Each has its own input format, its own output format, its own runtime characteristics, its own quality profile. Hard-coding any one of them into the pipeline would lock us in.

## Decision

Define an abstract base class `wirewright.placers.base.Placer` with a single method `place(schematic, hints) -> Schematic`. Every back end is an adapter that:

1. Translates IR to its native input format.
2. Calls the underlying engine.
3. Translates the engine's output back to IR with coordinates and wires populated.

The CLI selects a back end at runtime via `--placer`. Tests instantiate the back end directly.

## Rationale

This is the minimum viable abstraction. Placers genuinely have different invariants and capabilities; pretending otherwise produces leaky abstractions. A method signature with one input and one output is the smallest contract that still composes.

The `hints` parameter is the escape valve for placer-specific configuration: signal direction, aspect ratio target, density preference, pinned components from a pattern match. Placers ignore hints they don't understand.

## Rejected alternatives

- A unified placement DSL that all back ends consume. Rejected because it would force a lowest-common-denominator design that gets in the way of each engine's strengths.
- Direct subclassing of a base class with shared infrastructure. Rejected because the back ends share almost nothing in common other than the `place` signature.

## Consequences

- Each new placer is a single file under `src/wirewright/placers/` plus an entry in the CLI back-end registry.
- The grid_naive placer ships in v0.0.1 as the structural template for the other adapters. Its layout quality is intentionally trivial; it exists to prove the pipeline works end-to-end.
- Tests can run against any back end uniformly using a parameterized test class.
