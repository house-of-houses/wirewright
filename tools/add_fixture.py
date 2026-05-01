"""Drop a netlist into ``tests/fixtures/<tier>/`` and scaffold its description.md.

Usage::

    python tools/add_fixture.py path/to/circuit.net --tier medium \\
        --description "Eurorack VCA core, 12 components"
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path, help="Path to source .net file")
    parser.add_argument("--tier", choices=["easy", "medium", "hard"], required=True)
    parser.add_argument("--description", default="", help="Short description for description.md")
    args = parser.parse_args(argv)

    if not args.netlist.exists():
        print(f"netlist not found: {args.netlist}", file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parent.parent
    fixtures = repo_root / "tests/fixtures" / args.tier
    fixtures.mkdir(parents=True, exist_ok=True)

    dest_net = fixtures / args.netlist.name
    if dest_net.exists():
        print(f"already exists: {dest_net}", file=sys.stderr)
        return 1

    shutil.copy2(args.netlist, dest_net)

    template = (repo_root / "tests/fixtures/_TEMPLATE.description.md").read_text()
    description = template.replace("# <fixture-name>", f"# {args.netlist.stem}").replace(
        "**Tier:** easy | medium | hard", f"**Tier:** {args.tier}"
    )
    if args.description:
        placeholder = (
            "(2-3 sentences. Why this fixture is in the corpus and what placer behavior\n"
            "it exercises.)"
        )
        description = description.replace(placeholder, args.description)

    desc_path = fixtures / f"{args.netlist.stem}.description.md"
    desc_path.write_text(description)

    print(f"copied:  {dest_net}")
    print(f"created: {desc_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
