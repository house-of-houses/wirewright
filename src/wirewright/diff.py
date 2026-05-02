"""Structural diff between two ``.asc`` files.

Used by the ``wirewright diff`` subcommand to surface what the user
changed when they edit a placer-rendered schematic in LTspice. The
output is a feedback signal for placer improvements: components that
the user *moves* are placement disagreements; components they
*rotate* are orientation disagreements; wires they *redraw* are
routing disagreements.

Net-topology preservation is checked separately: the same multiset of
``(component_ref, pin_name)`` tuples per net should appear on both
sides. If not, the user changed connectivity (intentionally or via
edit slip), which is a different kind of feedback.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from wirewright.ir.model import Schematic
from wirewright.parse.ltspice_asc import parse_asc_text


@dataclass
class ComponentMove:
    ref: str
    old_xy: tuple[int, int]
    new_xy: tuple[int, int]

    @property
    def delta(self) -> tuple[int, int]:
        return (self.new_xy[0] - self.old_xy[0], self.new_xy[1] - self.old_xy[1])


@dataclass
class ComponentRotation:
    ref: str
    old_orientation: str
    new_orientation: str


@dataclass
class AscDiff:
    moved: list[ComponentMove] = field(default_factory=list)
    rotated: list[ComponentRotation] = field(default_factory=list)
    added_components: list[str] = field(default_factory=list)
    removed_components: list[str] = field(default_factory=list)
    wires_added: int = 0
    wires_removed: int = 0
    flags_added: int = 0
    flags_removed: int = 0
    connectivity_preserved: bool = True
    connectivity_notes: list[str] = field(default_factory=list)


def diff_asc_files(original: str, edited: str) -> AscDiff:
    """Diff two ``.asc`` text strings; return a structured :class:`AscDiff`."""
    a = parse_asc_text(original)
    b = parse_asc_text(edited)
    return _diff_schematics(a, b)


def _diff_schematics(a: Schematic, b: Schematic) -> AscDiff:
    diff = AscDiff()

    by_ref_a = {c.ref: c for c in a.components}
    by_ref_b = {c.ref: c for c in b.components}

    diff.added_components = sorted(set(by_ref_b) - set(by_ref_a))
    diff.removed_components = sorted(set(by_ref_a) - set(by_ref_b))

    for ref in sorted(set(by_ref_a) & set(by_ref_b)):
        ca, cb = by_ref_a[ref], by_ref_b[ref]
        if (ca.x, ca.y) != (cb.x, cb.y):
            assert ca.x is not None and ca.y is not None
            assert cb.x is not None and cb.y is not None
            diff.moved.append(ComponentMove(ref=ref, old_xy=(ca.x, ca.y), new_xy=(cb.x, cb.y)))
        if ca.orientation != cb.orientation:
            diff.rotated.append(
                ComponentRotation(
                    ref=ref, old_orientation=ca.orientation, new_orientation=cb.orientation
                )
            )

    wires_a = {(w.x1, w.y1, w.x2, w.y2) for w in a.wires}
    wires_b = {(w.x1, w.y1, w.x2, w.y2) for w in b.wires}
    diff.wires_added = len(wires_b - wires_a)
    diff.wires_removed = len(wires_a - wires_b)

    flags_a = {(f.x, f.y, f.net) for f in a.flags}
    flags_b = {(f.x, f.y, f.net) for f in b.flags}
    diff.flags_added = len(flags_b - flags_a)
    diff.flags_removed = len(flags_a - flags_b)

    sig_a = _connectivity_signature(a)
    sig_b = _connectivity_signature(b)
    if _multiset(sig_a) != _multiset(sig_b):
        diff.connectivity_preserved = False
        # Surface the asymmetric net signatures for diagnostics.
        only_in_a = sorted(_multiset(sig_a) - _multiset(sig_b))
        only_in_b = sorted(_multiset(sig_b) - _multiset(sig_a))
        if only_in_a:
            diff.connectivity_notes.append(f"nets only in original: {only_in_a}")
        if only_in_b:
            diff.connectivity_notes.append(f"nets only in edited: {only_in_b}")

    return diff


def _connectivity_signature(s: Schematic) -> dict[str, frozenset[tuple[str, str]]]:
    sig: dict[str, set[tuple[str, str]]] = {}
    for c in s.components:
        for pin_name, net_name in c.pins.items():
            sig.setdefault(net_name, set()).add((c.ref, pin_name))
    return {k: frozenset(v) for k, v in sig.items()}


def _multiset(sig: dict[str, frozenset[tuple[str, str]]]) -> frozenset[tuple[tuple[str, str], ...]]:
    return frozenset(tuple(sorted(v)) for v in sig.values())


def format_diff(diff: AscDiff) -> str:
    """Human-readable rendering of an :class:`AscDiff`."""
    lines: list[str] = []

    if diff.added_components:
        lines.append(f"Components added: {', '.join(diff.added_components)}")
    if diff.removed_components:
        lines.append(f"Components removed: {', '.join(diff.removed_components)}")

    if diff.moved:
        lines.append(f"Components moved ({len(diff.moved)}):")
        for m in diff.moved:
            dx, dy = m.delta
            sign_x = "+" if dx >= 0 else ""
            sign_y = "+" if dy >= 0 else ""
            lines.append(f"  {m.ref}: {m.old_xy} → {m.new_xy}    Δ({sign_x}{dx}, {sign_y}{dy})")

    if diff.rotated:
        lines.append(f"Components rotated ({len(diff.rotated)}):")
        for r in diff.rotated:
            lines.append(f"  {r.ref}: {r.old_orientation} → {r.new_orientation}")

    if diff.wires_added or diff.wires_removed:
        lines.append(f"Wires: +{diff.wires_added} added / -{diff.wires_removed} removed")
    if diff.flags_added or diff.flags_removed:
        lines.append(f"Flags: +{diff.flags_added} added / -{diff.flags_removed} removed")

    if diff.connectivity_preserved:
        lines.append("Net topology: preserved")
    else:
        lines.append("Net topology: CHANGED")
        for note in diff.connectivity_notes:
            lines.append(f"  {note}")

    if not lines:
        lines.append("(no differences)")

    return "\n".join(lines)
