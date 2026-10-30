"""PNG rendering for the VCoT loop.

Draws a wirewright :class:`Schematic` as a PNG image the MLLM can read
back. Fidelity is sufficient for the model to see component outlines,
pin positions, wire routing, and alignment — not pixel-identical to
LTspice. Matplotlib primitives, no external renderer dependency.

Deterministic: fixed figure size and dpi; axes bounds derived from
content with a fixed margin. Two identical inputs produce identical
bytes.

LTspice uses screen-space Y (positive down); matplotlib defaults to
math-space Y (positive up). The axes Y is inverted so that the rendered
image matches what LTspice shows the user.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive, deterministic backend

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.patches import Polygon, Rectangle

from wirewright.ir.model import Component, Flag, Schematic, Wire
from wirewright.symbols.builtin import (
    absolute_pin_position,
    rotate_offset,
    symbol_geometry,
)

_FIG_SIZE = (8, 8)  # inches
_DPI = 110
_MARGIN = 48  # IR grid units of padding around content
_PIN_RADIUS = 4  # IR units; drawn as filled circles for the model to see


@dataclass(frozen=True)
class _Bounds:
    xmin: int
    ymin: int
    xmax: int
    ymax: int


def _rotated_bbox_corners(
    comp: Component,
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Return the four corners of ``comp``'s bbox in absolute coords.

    Applies the component's orientation to the symbol's R0 bbox then
    translates by ``(comp.x, comp.y)``.
    """
    geom = symbol_geometry(comp.symbol)
    bx0, by0, bx1, by1 = geom.bbox
    r0_corners = [(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)]
    rotated = [rotate_offset(c, comp.orientation) for c in r0_corners]
    cx, cy = comp.x or 0, comp.y or 0
    return (
        (cx + rotated[0][0], cy + rotated[0][1]),
        (cx + rotated[1][0], cy + rotated[1][1]),
        (cx + rotated[2][0], cy + rotated[2][1]),
        (cx + rotated[3][0], cy + rotated[3][1]),
    )


def _schematic_bounds(sch: Schematic) -> _Bounds:
    xs: list[int] = []
    ys: list[int] = []
    for c in sch.components:
        if not c.is_placed:
            continue
        for px, py in _rotated_bbox_corners(c):
            xs.append(px)
            ys.append(py)
    for w in sch.wires:
        xs.extend([w.x1, w.x2])
        ys.extend([w.y1, w.y2])
    for f in sch.flags:
        xs.append(f.x)
        ys.append(f.y)
    if not xs:
        return _Bounds(-_MARGIN, -_MARGIN, _MARGIN, _MARGIN)
    return _Bounds(
        min(xs) - _MARGIN,
        min(ys) - _MARGIN,
        max(xs) + _MARGIN,
        max(ys) + _MARGIN,
    )


def _draw_grid(ax: Axes, bounds: _Bounds) -> None:
    """Faint 16-unit grid for visual reference."""
    step = 16
    x_start = (bounds.xmin // step) * step
    y_start = (bounds.ymin // step) * step
    for x in range(x_start, bounds.xmax + 1, step):
        ax.axvline(x, color="#eeeeee", linewidth=0.3, zorder=0)
    for y in range(y_start, bounds.ymax + 1, step):
        ax.axhline(y, color="#eeeeee", linewidth=0.3, zorder=0)


def _draw_component(ax: Axes, comp: Component) -> None:
    if not comp.is_placed:
        return
    corners = _rotated_bbox_corners(comp)
    poly = Polygon(
        corners,
        closed=True,
        fill=True,
        facecolor="#f5f5f5",
        edgecolor="#1f77b4",
        linewidth=1.2,
        zorder=2,
    )
    ax.add_patch(poly)

    # Label: component ref + symbol (+ value if present), inside the bbox.
    cx = sum(p[0] for p in corners) / 4
    cy = sum(p[1] for p in corners) / 4
    label = f"{comp.ref}\n{comp.symbol}"
    if comp.value:
        label = f"{label}\n{comp.value}"
    ax.text(
        cx,
        cy,
        label,
        ha="center",
        va="center",
        fontsize=6,
        family="monospace",
        zorder=3,
    )

    # Pin dots — the model needs to see where pins actually land.
    geom = symbol_geometry(comp.symbol)
    for pin_name in geom.pins:
        px, py = absolute_pin_position(
            (comp.x or 0, comp.y or 0),
            comp.symbol,
            pin_name,
            comp.orientation,
        )
        dot = Rectangle(
            (px - _PIN_RADIUS, py - _PIN_RADIUS),
            2 * _PIN_RADIUS,
            2 * _PIN_RADIUS,
            facecolor="#d62728",
            edgecolor="none",
            zorder=4,
        )
        ax.add_patch(dot)


def _draw_wire(ax: Axes, w: Wire) -> None:
    ax.plot(
        [w.x1, w.x2],
        [w.y1, w.y2],
        color="#2ca02c",
        linewidth=1.6,
        solid_capstyle="round",
        zorder=1,
    )


def _draw_flag(ax: Axes, f: Flag) -> None:
    label = "GND" if f.net == "0" else f.net
    ax.text(
        f.x,
        f.y,
        label,
        ha="center",
        va="center",
        fontsize=7,
        family="monospace",
        color="#9467bd",
        zorder=5,
        bbox={"facecolor": "white", "edgecolor": "#9467bd", "pad": 1},
    )


def render_schematic_png(sch: Schematic, out: Path | str) -> Path:
    """Render ``sch`` to a PNG at ``out`` and return the path.

    Deterministic for identical input: fixed figure size, dpi, and
    draw order.
    """
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    bounds = _schematic_bounds(sch)
    fig, ax = plt.subplots(figsize=_FIG_SIZE, dpi=_DPI)
    try:
        ax.set_aspect("equal", adjustable="datalim")
        ax.set_xlim(bounds.xmin, bounds.xmax)
        ax.set_ylim(bounds.ymax, bounds.ymin)  # inverted — LTspice Y-down
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_color("#cccccc")

        _draw_grid(ax, bounds)
        for w in sch.wires:
            _draw_wire(ax, w)
        for c in sch.components:
            _draw_component(ax, c)
        for f in sch.flags:
            _draw_flag(ax, f)

        fig.tight_layout(pad=0.5)
        fig.savefig(out_path, dpi=_DPI, bbox_inches="tight")
    finally:
        plt.close(fig)

    return out_path
