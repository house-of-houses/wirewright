# ADR 0004: ELK and HOLA as the two real placement baselines

**Status**: Accepted

**Date**: 2026-05-01

## Context

The v2 deep-research pass (see `docs/research/`) identified two distinct families of high-quality open-source placers that are well-suited to circuit schematics: layered/Sugiyama (best representative: ELK Layered) and stress-majorization with port constraints (best representative: HOLA in libdialect). They produce visibly different output styles for the same input.

Sugiyama-style produces strict left-to-right layered output, ideal for circuits with strong directional flow (signal chains, CV processors).

HOLA produces compact, symmetric output that better matches how humans draw analog circuits with feedback and balanced sections.

## Decision

Ship both as first-class placer back ends. Do not pick one over the other. Let the user choose with `--placer` and document our opinion (in `docs/notes/elk-vs-hola.md`, written after Phase 4) about which works better for which kinds of circuits.

## Rationale

Different circuits genuinely benefit from different layout philosophies. A Eurorack VCO with feedback wants HOLA. A multi-stage filter chain wants ELK. There is no single right answer at the algorithm level; the right answer is at the per-circuit level.

Both are mature, both are open source, both are actively maintained as of 2025-2026 (ELK with 114 commits in the last 12 months, HOLA recently extended in March 2026 by ARCOL). The cost of supporting both is real but bounded.

## Rejected alternatives

- ELK only. Easier to ship, but cuts us off from the algorithm that the deep research identified as the closest match for analog aesthetics.
- HOLA only. Harder to install (C++ build), and weaker on circuits with strong directional flow.
- Roll-our-own placer from scratch. Rejected for v0.x; revisit only if both off-the-shelf options prove unworkable.

## Consequences

- We invest in the placer adapter pattern (ADR 0003) seriously, not nominally.
- We have a Node dependency for ELK and a C++ build dependency for HOLA. The CLI must degrade gracefully when one is missing.
- The pattern library (Phase 5) must produce hints in a form both ELK and HOLA can consume. Concretely, "pinned positions" and "alignment constraints" are the two universal output shapes.
- v0.1 ships with at least ELK working. HOLA in v0.1 is desirable but not required; can slip to v0.2.
