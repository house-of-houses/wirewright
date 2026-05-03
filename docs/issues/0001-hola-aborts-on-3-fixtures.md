# Issue 0001: HOLA C++ aborts on 3 canonical fixtures

**Opened:** 2026-05-02
**Resolved:** 2026-05-03 (fix path #2 — `_biconnect_leaf_extras` retry)
**Severity:** Quality (workaround exists; HOLA layout unavailable for these)
**Tags:** hola, placer, libdialect, upstream

## Symptom

Direct `wirewright render <fixture> --placer hola` aborts with:

```
Assertion failed: (u != nullptr), function identifyExternalFace,
file faces.cpp, line 185.
PlacerEngineError: hola subprocess failed (signal 6)
```

on these three fixtures:

- `tests/fixtures/medium/tb303-vco-saw-cliptop.net`
- `tests/fixtures/medium/tb303-vco-saw-cliptop-bottom.net`
- `tests/fixtures/hard/tb303-vco-integrated.net`

## Status

- **Process survives.** v0.1's subprocess isolation in
  `src/wirewright/placers/_hola_subprocess.py` catches the C++ abort and
  surfaces it as `PlacerEngineError`.
- **`--placer auto` works.** The v0.2 AutoPlacer (`src/wirewright/placers/auto.py`)
  silently falls back to `NaivePlacer` on these fixtures, so the user gets
  a renderable `.asc` — just naive's grid layout, not HOLA's.
- **Direct `--placer hola` does NOT work** for these fixtures and won't
  until the issue is fixed at one of the layers below.

## Root cause

The graphs HOLA receives (after `_stitching_edges` adds virtual edges to
connect disconnected components) have properties HOLA's
`identifyExternalFace` step rejects. NetworkX confirms:

| fixture | nodes | edges | planar | biconnected |
|---------|------:|------:|:------:|:-----------:|
| tb303-vco-saw-cliptop | 13 | 22 | False | False |
| tb303-vco-saw-cliptop-bottom | 14 | 27 | False | False |
| tb303-vco-integrated | 37 | 49 | False | False |

3 of 3 are non-planar after stitching. Cut vertices: `Q_CLAMP`, `D25`,
`U_BUF.BAMP`, `VSS` for the cliptops; `R_TOP`, `E_BUF`, `Q1`, `Q2`,
`Q_CAS` for vco-integrated.

(`tb303-voice-chain` is planar after stitching but not biconnected — it
used to abort too, until subprocess isolation fixed *that* particular
case. That suggests biconnectivity isn't a hard requirement for HOLA;
some other property of the cliptop/integrated graphs is.)

## Fix paths (any one works; in increasing investment)

1. **Stay with `--placer auto`.** Already shipped. Documented in
   `placer-interface.md`. Acceptable indefinitely if the user is okay
   with naive's layout for these 3 fixtures.

2. **Wirewright-side graph pre-conditioning.** Investigate which graph
   transformation produces a HOLA-acceptable input. Candidates:
   (a) drop edges that create the non-planar K5/K3,3 subdivision after
   stitching; (b) replace stitching-chain edges with a star (one virtual
   hub node connected to all components); (c) try without stitching and
   see if HOLA's disconnected-graph abort is more recoverable than its
   planarity abort. Trial-and-error work; ~1 session.

3. **Upstream fix in `shakfu/hola-graph` or `mjwybrow/adaptagrams`.**
   File an issue with one of the failing graphs as a minimal repro.
   Either the upstream maintainer hardens `identifyExternalFace` to
   handle these inputs (best outcome), or documents the constraint we
   should pre-screen for. Out-of-band timeline.

## Quick-repro snippet

```python
from pathlib import Path
from wirewright.parse.spice import parse_spice_file
from wirewright.placers.hola import HolaPlacer
from wirewright.placers.base import PlacerEngineError

for f in [
    "tests/fixtures/medium/tb303-vco-saw-cliptop.net",
    "tests/fixtures/medium/tb303-vco-saw-cliptop-bottom.net",
    "tests/fixtures/hard/tb303-vco-integrated.net",
]:
    try:
        HolaPlacer().place(parse_spice_file(Path(f)))
        print(f"{f}: PLACED")
    except PlacerEngineError as e:
        print(f"{f}: {str(e)[:100]}")
```

## Resolution (2026-05-03)

Fix path #2 landed: `src/wirewright/placers/hola.py::_biconnect_leaf_extras`
chains the leaves of every articulation point into a path, supplying
virtual edges that give HOLA's planar embedding a well-defined external
face. The chaining is **applied only on retry** after a first attempt
aborts with `identifyExternalFace`, because pre-emptive chaining
collapses small graphs (e.g. divider's 3-node path) into K3 — which HOLA
also rejects.

All 3 fixtures now render under `--placer hola` directly; the integration
test `test_hola_renders_canonical_fixture` covers them.

A per-component approach (fix path #2c) was investigated and discarded:
the largest connected component of each fixture is itself the graph
HOLA aborts on, so per-component layout doesn't help — the offending
topology is inside one component.
