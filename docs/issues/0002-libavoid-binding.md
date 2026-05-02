# Issue 0002: libavoid Python binding does not exist

**Opened:** 2026-05-02
**Severity:** Quality (multi-obstacle routing in v0.2 is pure-Python A-ish; libavoid would be better)
**Tags:** routing, upstream, optional

## Symptom

`wirewright`'s pure-Python obstacle-aware router (`routing/orthogonal.py`)
covers L-shape and Z-shape detours. It does not handle dense feedback
loops or multi-obstacle dodges that require a full Manhattan-routing
algorithm. libavoid (Adaptagrams, C++, used by Inkscape) would.

## State of the world (re-confirmed 2026-05-02)

- `hola_graph._core.avoid` exposes geometry primitives only: `Box`,
  `Polygon`, `Edge`, `Point`, `Rectangle`, `PolygonInterface`,
  `ReferencingPolygon`. **No `Router`, `ConnRef`, `ShapeRef`,
  `ConnEnd`, `Polyline`** — i.e., none of libavoid's actual connector
  routing API.
- PyPI: `pylibavoid`, `libavoid`, `libavoid-python`, `adaptagrams`,
  `pyadaptagrams` — none exist.
- Inkscape uses libavoid via direct C++ link, not Python.

## Why we don't fix this in wirewright proper

Writing the binding ourselves is a 3-5 day pybind11 + adaptagrams build
project. It would mean:

1. Forking `shakfu/hola-graph` (or starting from `mjwybrow/adaptagrams`).
2. Adding pybind11 wrappers for `Avoid::Router`, `ConnRef`, `ConnEnd`,
   `ShapeRef`, `JunctionRef`, `Polyline`, the `RoutingParameter` enum.
3. Building the C++ on macOS arm64 + Linux x86_64 wheels.
4. Maintaining the wrapper as upstream changes.

This is its own project, not a wirewright sub-task. Out of scope for
v0.2; out of scope for v0.3 unless someone else writes the binding or
we decide the routing-quality ceiling justifies it.

## Watch list (any of these unblocks libavoid integration)

- A new PyPI package wrapping libavoid's `Router`. Check periodically
  via `pip index versions <name>` for: `pylibavoid`, `libavoid`,
  `adaptagrams`.
- Upstream `shakfu/hola-graph` exposing `avoid::Router` to Python.
  Watch <https://github.com/shakfu/hola-graph/issues> and the changelog.
- A standalone Inkscape extension or other tool publishing C++ bindings
  to PyPI.
- Someone (us or external) writing the binding as a separate
  `wirewright-libavoid` package.

## What we ship instead in v0.2

`routing/orthogonal.py::route_avoiding` does:

1. Try the 2 L-shape options (HV, VH).
2. If both cross obstacles, try 4 Z-shape options routing around the
   obstacle-bbox extremes (top, bottom, left, right of all obstacles).
3. Pick the path with fewest crossings, tie-break by total length.

This handles single-obstacle dodges and most two-obstacle cases. It
does not handle dense feedback (3+ overlapping obstacle crossings)
or congested routing channels — those stay as visual issues until
libavoid is reachable.

## Quick measure of when this issue becomes urgent

When `tools/review.py` results have a recurring "needs-routing" tag in
the verdict column with category "dense-feedback" or "bypass-routing"
on >25% of fixtures, the pure-Python router has hit its ceiling and
the libavoid investment is justified.

Until then, keep the watch list and ship without it.
