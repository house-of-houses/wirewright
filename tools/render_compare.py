"""Side-by-side comparison of placers on a fixture.

Phase 4 deliverable. Stub for now.

Planned use::

    uv run python tools/render_compare.py tests/fixtures/medium

Renders the fixture's netlist with every available placer and writes the
results into a `_compare/` subdirectory plus an HTML report.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "render_compare.py: Phase 4 deliverable. See docs/PLAN.md.\n"
        "For now, run: wirewright render <netlist> -o <out.asc> --placer <name>"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
