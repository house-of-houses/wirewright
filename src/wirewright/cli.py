"""Command-line interface for wirewright.

Usage::

    wirewright --help
    wirewright version
    wirewright demo
    wirewright render <netlist> -o <out.asc> [--placer naive|hola]
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from wirewright import __version__
from wirewright.emit.asc import emit_asc, write_asc
from wirewright.ir.model import Component, Net, Schematic
from wirewright.parse.spice import parse_spice_file
from wirewright.placers import get_placer

app = typer.Typer(
    name="wirewright",
    help="Auto-generate readable LTspice .asc schematics from SPICE netlists.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Print the installed wirewright version."""
    console.print(f"wirewright [bold]{__version__}[/bold]")


@app.command()
def demo(
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Where to write the .asc file (default: stdout)."),
    ] = None,
    placer: Annotated[
        str,
        typer.Option("--placer", help="Which placer to use."),
    ] = "naive",
) -> None:
    """Run a hard-coded 2-resistor circuit through the full pipeline.

    Useful as a sanity check that everything is wired up correctly.
    """
    schematic = _build_demo_schematic()
    placer_obj = get_placer(placer)
    placed = placer_obj.place(schematic)
    asc_text = emit_asc(placed)

    if output is None:
        console.print(Panel.fit(asc_text, title=f"Demo .asc (placer: {placer})"))
    else:
        write_asc(placed, output)
        console.print(f"[green]Wrote[/green] {output}")


@app.command()
def render(
    netlist: Annotated[Path, typer.Argument(help="Path to the SPICE netlist file.")],
    output: Annotated[
        Path,
        typer.Option("-o", "--output", help="Where to write the .asc file."),
    ],
    placer: Annotated[
        str,
        typer.Option("--placer", help="Which placer to use."),
    ] = "naive",
    use_patterns: Annotated[
        bool,
        typer.Option(
            "--use-patterns",
            help="Detect analog idioms (diff pair, current mirror, RC filter, …) and pin them to canonical positions before placement.",
        ),
    ] = False,
) -> None:
    """Render a SPICE netlist to an LTspice .asc file."""
    if not netlist.exists():
        console.print(f"[red]Netlist not found:[/red] {netlist}")
        raise typer.Exit(code=1)

    schematic = parse_spice_file(netlist)
    placer_obj = get_placer(placer)
    hints: dict[str, object] | None = None
    if use_patterns:
        from wirewright.patterns.orchestrate import build_hints_from_patterns

        full_hints = build_hints_from_patterns(schematic)
        matches = full_hints.pop("_matches", [])
        hints = full_hints
        if matches:
            summary = ", ".join(
                f"{m.pattern_name}({list(m.role_to_ref.values())})" for m in matches
            )
            console.print(f"[cyan]Patterns matched:[/cyan] {summary}")
        else:
            console.print("[yellow]No patterns matched in this netlist.[/yellow]")
    placed = placer_obj.place(schematic, hints=hints)
    write_asc(placed, output)
    console.print(
        f"[green]Rendered[/green] {netlist} → {output} "
        f"({len(placed.components)} components, {len(placed.wires)} wires)"
    )


@app.command()
def placers() -> None:
    """List available placement back ends."""
    from wirewright.placers import registry

    console.print("[bold]Available placers:[/bold]")
    for name in sorted(registry):
        cls = registry[name]
        doc = (cls.__doc__ or "").strip().splitlines()[0] if cls.__doc__ else ""
        console.print(f"  [cyan]{name}[/cyan]  {doc}")


def _build_demo_schematic() -> Schematic:
    """Two resistors in series between VIN and GND, sharing node N1."""
    return Schematic(
        title="wirewright demo: two resistors in series",
        components=[
            Component(
                ref="R1",
                symbol="res",
                value="10k",
                pins={"1": "vin", "2": "n1"},
                spice_prefix="R",
            ),
            Component(
                ref="R2",
                symbol="res",
                value="10k",
                pins={"1": "n1", "2": "0"},
                spice_prefix="R",
            ),
        ],
        nets=[
            Net(name="vin"),
            Net(name="n1"),
            Net(name="0", is_ground=True),
        ],
        directives=[".tran 1m"],
    )


if __name__ == "__main__":
    app()
