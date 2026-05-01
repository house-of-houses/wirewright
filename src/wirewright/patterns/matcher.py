"""Subgraph isomorphism matcher for analog idiom recognition.

Walks an unplaced :class:`Schematic` looking for instances of registered
YAML templates via NetworkX VF2 (``isomorphism.GraphMatcher``). Returns
a list of :class:`PatternMatch` records each carrying a role-to-ref map and
the placement transforms the placer should respect.

See ``docs/specs/pattern-library.md`` for the grammar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx  # type: ignore[import-untyped]
from networkx.algorithms import isomorphism  # type: ignore[import-untyped]

from wirewright.ir.model import Schematic
from wirewright.patterns.template import (
    PlacementHint,
    Template,
    TopologyConstraint,
    load_default_library,
)


@dataclass(frozen=True)
class PatternMatch:
    """One successful match of a template against the schematic."""

    pattern_name: str
    pattern_version: int
    priority: int
    role_to_ref: dict[str, str]
    placement: list[PlacementHint] = field(default_factory=list)


def find_matches(
    schematic: Schematic, templates: list[Template] | None = None
) -> list[PatternMatch]:
    """Find every match of every template; resolve overlap via priority."""
    if templates is None:
        templates = load_default_library()

    graph = _schematic_to_graph(schematic)
    raw_matches: list[PatternMatch] = []

    for template in templates:
        for role_to_ref in _match_template(graph, template, schematic):
            raw_matches.append(
                PatternMatch(
                    pattern_name=template.name,
                    pattern_version=template.version,
                    priority=template.priority,
                    role_to_ref=role_to_ref,
                    placement=template.placement,
                )
            )

    return _resolve_overlaps(raw_matches)


def _schematic_to_graph(schematic: Schematic) -> nx.Graph:
    """Build a graph: components as nodes, shared non-power/ground nets as edges."""
    g = nx.Graph()
    power_or_ground = {n.name for n in schematic.nets if n.is_power or n.is_ground}
    for c in schematic.components:
        g.add_node(c.ref, symbol=c.symbol, spice_prefix=c.spice_prefix)
    net_pins: dict[str, list[tuple[str, str]]] = {}
    for c in schematic.components:
        for pin_name, net_name in c.pins.items():
            if net_name in power_or_ground:
                continue
            net_pins.setdefault(net_name, []).append((c.ref, pin_name))
    for pins in net_pins.values():
        for i in range(len(pins)):
            for j in range(i + 1, len(pins)):
                ra, _pa = pins[i]
                rb, _pb = pins[j]
                if ra != rb:
                    g.add_edge(ra, rb)
    return g


def _match_template(
    graph: nx.Graph, template: Template, schematic: Schematic
) -> list[dict[str, str]]:
    """Return canonical role-to-ref mappings satisfying the template."""
    pattern = nx.Graph()
    for c in template.components:
        pattern.add_node(c.role, symbol=c.symbol)

    same_constraints = [c for c in template.topology if c.kind == "same"]
    diff_constraints = [c for c in template.topology if c.kind == "diff"]
    ground_constraints = [c for c in template.topology if c.kind == "ground"]

    # Pattern edges: any "same" constraint between two distinct roles requires
    # a graph edge (some net joins them). Multiple constraints between the
    # same role pair collapse to a single edge in the simple graph view.
    for sc in same_constraints:
        if sc.b is None:
            continue
        if sc.a[0] != sc.b[0]:
            pattern.add_edge(sc.a[0], sc.b[0])

    if pattern.number_of_nodes() == 0:
        return []

    matcher = isomorphism.GraphMatcher(
        graph,
        pattern,
        node_match=lambda host, pat: host.get("symbol") == pat.get("symbol"),
    )

    canonical_by_refset: dict[frozenset[str], dict[str, str]] = {}
    for mapping in matcher.subgraph_isomorphisms_iter():
        role_to_ref = {role: ref for ref, role in mapping.items()}
        if not _check_full_topology(
            role_to_ref, schematic, same_constraints, diff_constraints, ground_constraints
        ):
            continue
        ref_set = frozenset(role_to_ref.values())
        # Canonicalize: keep the lex-smallest mapping per ref-set so output
        # is deterministic across runs.
        existing = canonical_by_refset.get(ref_set)
        candidate_key = tuple(sorted(role_to_ref.items()))
        if existing is None or candidate_key < tuple(sorted(existing.items())):
            canonical_by_refset[ref_set] = role_to_ref

    return list(canonical_by_refset.values())


def _check_full_topology(
    role_to_ref: dict[str, str],
    schematic: Schematic,
    same: list[TopologyConstraint],
    diff: list[TopologyConstraint],
    ground: list[TopologyConstraint],
) -> bool:
    """Verify all topology constraints hold for this role-to-ref binding."""
    ground_nets = {n.name for n in schematic.nets if n.is_ground or n.name == "0"}
    by_ref = {c.ref: c for c in schematic.components}

    def net_at(role: str, pin: str) -> str | None:
        ref = role_to_ref.get(role)
        if ref is None:
            return None
        comp = by_ref.get(ref)
        if comp is None:
            return None
        return comp.pins.get(pin)

    for c in same:
        if c.b is None:
            continue
        n1 = net_at(c.a[0], c.a[1])
        n2 = net_at(c.b[0], c.b[1])
        if n1 != n2 or n1 is None:
            return False
    for c in diff:
        if c.b is None:
            continue
        n1 = net_at(c.a[0], c.a[1])
        n2 = net_at(c.b[0], c.b[1])
        if n1 is None or n2 is None or n1 == n2:
            return False
    for c in ground:
        n = net_at(c.a[0], c.a[1])
        if n not in ground_nets:
            return False
    return True


def _resolve_overlaps(matches: list[PatternMatch]) -> list[PatternMatch]:
    """Higher priority wins; drop lower-priority matches sharing any ref."""
    matches_sorted = sorted(matches, key=lambda m: (-m.priority, m.pattern_name))
    accepted: list[PatternMatch] = []
    used_refs: set[str] = set()
    for m in matches_sorted:
        refs = set(m.role_to_ref.values())
        if refs & used_refs:
            continue
        accepted.append(m)
        used_refs |= refs
    return accepted
