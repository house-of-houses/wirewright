"""Side-by-side placer comparison.

Renders the given fixture (or every ``.net`` file in a directory) under each
available placer and writes results to an output directory. Each placer's
output goes to ``<out>/<fixture-stem>.<placer>.asc``.

Usage::

    uv run python tools/render_compare.py tests/fixtures/medium/tb303-envelope.net
    uv run python tools/render_compare.py tests/fixtures/easy --out _cmp
    uv run python tools/render_compare.py fixture.net --placers naive elk
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from wirewright.emit.asc import write_asc
from wirewright.parse.spice import parse_spice_file
from wirewright.placers import get_placer, registry


def _render_one(
    fixture: Path, placer_name: str, out_dir: Path, verbose: bool = False
) -> Path | None:
    """Render fixture under the named placer; return path or None on failure."""
    try:
        sch = parse_spice_file(fixture)
        placer = get_placer(placer_name)
        placed = placer.place(sch)
    except Exception as e:
        msg = f"  {placer_name}: FAILED ({type(e).__name__}: {e})"
        print(msg, file=sys.stderr)
        if verbose:
            traceback.print_exc(file=sys.stderr)
        return None
    out_path = out_dir / f"{fixture.stem}.{placer_name}.asc"
    write_asc(placed, out_path)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Fixture file or directory of fixtures")
    parser.add_argument("--out", type=Path, default=Path("compare_out"), help="Output directory")
    parser.add_argument(
        "--placers",
        nargs="+",
        default=sorted(registry),
        help="Placers to compare (default: all registered)",
    )
    parser.add_argument("--verbose", action="store_true", help="Print full tracebacks on failure")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    fixtures: list[Path] = sorted(args.input.glob("*.net")) if args.input.is_dir() else [args.input]

    for fixture in fixtures:
        print(f"=== {fixture.name}")
        for placer_name in args.placers:
            out_path = _render_one(fixture, placer_name, args.out, args.verbose)
            if out_path is not None:
                print(f"  {placer_name}: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
