# ADR-0005: HOLA as the only placer; ELK removed

**Status:** Accepted (supersedes ADR-0004).

**Date:** 2026-05-01.

## Context

ADR-0004 committed to shipping ELK Layered and HOLA as dual placement
back ends behind the `Placer` interface, with the user picking via
`--placer`. The rationale was that the two algorithms produce visibly
different output on the same input (Sugiyama-layered vs symmetric stress
majorization) and different circuits genuinely benefit from different
choices.

Phase 3 (ELK) and Phase 4 (HOLA) shipped in v0.1. The user then ran
`tools/render_compare.py` across all 21 canonical TB-303 fixtures with
both placers, opened the resulting `.asc` files in LTspice, and
empirically judged HOLA the better placer **by far** for this domain.

Subprocess isolation around HOLA (added during the same session) made
HOLA's C++ aborts recoverable, lifting HOLA from 17/21 to 18/21
successful renders. The remaining 3 abort-fixtures (`tb303-vco-saw-cliptop`,
`tb303-vco-saw-cliptop-bottom`, `tb303-vco-integrated`) genuinely
overwhelm HOLA's `faces.cpp::identifyExternalFace` step — but ELK's
output on those circuits was not better in any way that matched the
user's taste; ELK simply produced different bad output.

## Decision

ELK is removed from the codebase. HOLA is the only placer.

The `Placer` ABC, the `--placer` flag, and the registry stay. They cost
nothing if HOLA remains the only entry, and they make a future second
back end land cleanly if one ever genuinely needs to (e.g. a port-aware
HOLA variant via libdialect, or a pattern-driven custom placer).

The 3 HOLA-abort fixtures are recorded as known limitations against
HOLA itself rather than as a reason to keep ELK around. Workarounds for
those (graph pre-conditioning to satisfy HOLA's biconnectivity-ish
requirements, or upstream fixes to libdialect) belong in the v0.2
backlog.

## Consequences

**Removed from the repo:**
- `src/wirewright/placers/elk.py`
- `tools/elk-bridge/` (entire directory; the Node bridge and `elkjs` dependency)
- `tests/unit/test_elk.py`, `tests/integration/test_elk_e2e.py`, `tests/integration/test_elk_render.py`
- ELK references in `pyproject.toml`, `.github/workflows/ci.yml` (Node setup), README, CLAUDE.md, `docs/design.md`, `docs/PLAN.md`, `docs/specs/*.md`
- `docs/notes/elk-vs-hola.md` (the comparison was the spike; spike result is recorded *in this ADR*)
- `docs/plans/phase-3.md`, `phase-3.review.md` (obsolete by the rephasing)

**Phasing (post-decision):**
- **Phase 0:** bootstrap (done).
- **Phase 1:** IR + ASC emitter (done).
- **Phase 2:** SPICE parser (done).
- **Phase 3:** HOLA + libavoid + expanded fixtures. The pipeline becomes
  real: `pyhola` build documented, `placers/hola.py` already implemented,
  `routing/orthogonal.py` becomes a libavoid wrapper, 8–12 expanded
  fixtures with HOLA output reviewed by the user and a "verdict + failure
  category" recorded for each.
- **Phase 4 (was 5):** pattern recognition driven by Phase 3's failure
  log. Patterns aren't written speculatively; they're written to fix the
  categorized failures from Phase 3. Much more focused than the original
  "ship a starter library and hope" plan.
- **No Phase 5.** Phase 4 is the last phase before v0.1 ships.

ADR-0004 stays in the repo for history (superseded but not deleted), so
the "why we tried two back ends" question has a documented answer when
re-reading commits years from now.

## Lesson

Spike early, decide early, delete early. The Phase 3+4 ELK/HOLA dual-track
shipped exactly to make this comparison possible; once the verdict landed,
keeping ELK would be sunk-cost code that adds complexity to every future
change. YAGNI applies: a future second placer can be added back in days
if the need is real, and re-adding under known requirements is cheaper
than maintaining unused code under unknown requirements.
