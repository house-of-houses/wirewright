"""Render every fixture x every placer and emit a markdown verdict table.

Usage::

    uv run python tools/review.py --out review.md
    uv run python tools/review.py --tier medium --out medium-review.md

The output table has rows = fixtures x placers, columns = fixture name,
placer, status (rendered / aborted / parse-error), file size, components
count, wire count, blank "verdict" and "category" columns for the user
to fill in after opening the .asc files in LTspice.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wirewright.emit.asc import emit_asc
from wirewright.parse.spice import parse_spice_file
from wirewright.placers import get_placer, registry


def _render_one(fixture: Path, placer_name: str, asc_out: Path) -> dict[str, str]:
    """Render one fixture+placer and return a row dict for the markdown table."""
    row = {
        "fixture": fixture.stem,
        "placer": placer_name,
        "status": "rendered",
        "size": "-",
        "components": "-",
        "wires": "-",
        "verdict": "",
        "category": "",
    }
    try:
        sch = parse_spice_file(fixture)
        placer = get_placer(placer_name)
        placed = placer.place(sch)
        asc_text = emit_asc(placed)
        out_path = asc_out / f"{fixture.stem}.{placer_name}.asc"
        out_path.write_text(asc_text)
        row.update(
            size=str(len(asc_text)),
            components=str(len(placed.components)),
            wires=str(len(placed.wires)),
        )
    except Exception as e:
        kind = type(e).__name__
        msg = str(e)[:80]
        row["status"] = f"FAILED ({kind}: {msg})"
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=["easy", "medium", "hard", "all"], default="all")
    parser.add_argument("--out", type=Path, default=Path("review.md"))
    parser.add_argument(
        "--asc-out",
        type=Path,
        default=Path("review_asc"),
        help="Where to write the rendered .asc files",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    fixtures_root = repo_root / "tests/fixtures"
    tiers = ["easy", "medium", "hard"] if args.tier == "all" else [args.tier]
    args.asc_out.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    for tier in tiers:
        for net in sorted((fixtures_root / tier).glob("*.net")):
            for placer_name in sorted(registry):
                rows.append(_render_one(net, placer_name, args.asc_out))

    md = ["# Render review", ""]
    md.append("Open each rendered `.asc` in LTspice. Fill in the **verdict**")
    md.append("(✓ acceptable / ⚠ needs-pattern / ⚠ needs-routing / ✗ aborted)")
    md.append("and **category** (bypass-routing / no-symmetry / dense-feedback /")
    md.append("dispersed-layout / other) per row. Phase 4 priorities draw from")
    md.append("the populated table.")
    md.append("")
    md.append("| fixture | placer | status | size | components | wires | verdict | category |")
    md.append("|---------|--------|--------|-----:|-----------:|------:|---------|----------|")
    for r in rows:
        md.append(
            f"| {r['fixture']} | {r['placer']} | {r['status']} | "
            f"{r['size']} | {r['components']} | {r['wires']} | "
            f"{r['verdict']} | {r['category']} |"
        )
    args.out.write_text("\n".join(md) + "\n")
    print(f"wrote {args.out} ({len(rows)} rows)")
    print(f"rendered .asc files in {args.asc_out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
