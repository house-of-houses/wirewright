"""Per-template matcher tests."""

from __future__ import annotations

from wirewright.ir.model import Component, Net, Schematic
from wirewright.patterns.matcher import find_matches


def _rc_lowpass_schematic() -> Schematic:
    return Schematic(
        components=[
            Component(ref="R1", symbol="res", pins={"1": "vin", "2": "n1"}),
            Component(ref="C1", symbol="cap", pins={"1": "n1", "2": "0"}),
        ],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
    )


def _rc_highpass_schematic() -> Schematic:
    return Schematic(
        components=[
            Component(ref="C1", symbol="cap", pins={"1": "vin", "2": "n1"}),
            Component(ref="R1", symbol="res", pins={"1": "n1", "2": "0"}),
        ],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
    )


def _diff_pair_npn_schematic() -> Schematic:
    return Schematic(
        components=[
            Component(
                ref="Q1",
                symbol="npn",
                pins={"C": "out_p", "B": "in_p", "E": "tail"},
                spice_prefix="Q",
                spice_model="QN3904",
            ),
            Component(
                ref="Q2",
                symbol="npn",
                pins={"C": "out_n", "B": "in_n", "E": "tail"},
                spice_prefix="Q",
                spice_model="QN3904",
            ),
        ],
        nets=[Net("out_p"), Net("out_n"), Net("in_p"), Net("in_n"), Net("tail")],
    )


def _current_mirror_npn_schematic() -> Schematic:
    """Q_REF diode-connected (B and C tied), Q_OUT shares its base."""
    return Schematic(
        components=[
            Component(
                ref="Q_REF",
                symbol="npn",
                pins={"C": "bias", "B": "bias", "E": "0"},
                spice_prefix="Q",
                spice_model="QN3904",
            ),
            Component(
                ref="Q_OUT",
                symbol="npn",
                pins={"C": "out", "B": "bias", "E": "0"},
                spice_prefix="Q",
                spice_model="QN3904",
            ),
        ],
        nets=[Net("bias"), Net("out"), Net("0", is_ground=True)],
    )


def _common_emitter_schematic() -> Schematic:
    return Schematic(
        components=[
            Component(
                ref="Q1",
                symbol="npn",
                pins={"C": "out", "B": "in", "E": "ne"},
                spice_prefix="Q",
                spice_model="QN3904",
            ),
            Component(ref="Rc", symbol="res", pins={"1": "vcc", "2": "out"}),
            Component(ref="Re", symbol="res", pins={"1": "ne", "2": "0"}),
        ],
        nets=[Net("out"), Net("in"), Net("ne"), Net("vcc"), Net("0", is_ground=True)],
    )


def test_rc_lowpass_match() -> None:
    matches = find_matches(_rc_lowpass_schematic())
    rc = [m for m in matches if m.pattern_name == "rc_lowpass"]
    assert len(rc) == 1
    assert rc[0].role_to_ref == {"r": "R1", "c": "C1"}


def test_rc_highpass_match() -> None:
    matches = find_matches(_rc_highpass_schematic())
    rc = [m for m in matches if m.pattern_name == "rc_highpass"]
    assert len(rc) == 1
    assert rc[0].role_to_ref == {"c": "C1", "r": "R1"}


def test_diff_pair_npn_match() -> None:
    matches = find_matches(_diff_pair_npn_schematic())
    dp = [m for m in matches if m.pattern_name == "diff_pair_npn"]
    assert len(dp) == 1
    assert set(dp[0].role_to_ref.values()) == {"Q1", "Q2"}


def test_current_mirror_npn_match() -> None:
    matches = find_matches(_current_mirror_npn_schematic())
    cm = [m for m in matches if m.pattern_name == "current_mirror_npn"]
    assert len(cm) == 1
    assert cm[0].role_to_ref == {"q_ref": "Q_REF", "q_out": "Q_OUT"}


def test_common_emitter_match() -> None:
    matches = find_matches(_common_emitter_schematic())
    ce = [m for m in matches if m.pattern_name == "common_emitter_npn"]
    assert len(ce) == 1
    assert ce[0].role_to_ref == {"q": "Q1", "rc": "Rc", "re": "Re"}


def test_unrelated_circuit_no_matches() -> None:
    s = Schematic(
        components=[Component(ref="V1", symbol="voltage", pins={"+": "vin", "-": "0"})],
        nets=[Net("vin"), Net("0", is_ground=True)],
    )
    assert find_matches(s) == []


def test_match_is_deterministic() -> None:
    """Symmetric patterns (diff pair) must produce identical output across runs."""
    s = _diff_pair_npn_schematic()
    runs = [find_matches(s) for _ in range(5)]
    keyed = [
        sorted((m.pattern_name, tuple(sorted(m.role_to_ref.items()))) for m in run) for run in runs
    ]
    assert all(k == keyed[0] for k in keyed)


def test_priority_resolves_overlap() -> None:
    """A circuit that matches both diff_pair_npn (priority 200) and (hypothetically)
    a low-priority overlap should keep the diff_pair_npn match. Diff pair has
    no overlapping NPN-only patterns in the v0.1 library, so just verify the
    standalone diff pair survives.
    """
    matches = find_matches(_diff_pair_npn_schematic())
    assert any(m.pattern_name == "diff_pair_npn" for m in matches)


def test_matches_to_pinned_hints_applies_dx_dy() -> None:
    from wirewright.patterns.orchestrate import matches_to_pinned_hints
    from wirewright.patterns.template import PlacementHint
    from wirewright.patterns.matcher import PatternMatch

    matches = [
        PatternMatch(
            pattern_name="rc_lowpass",
            pattern_version=1,
            priority=100,
            role_to_ref={"r": "R1", "c": "C1"},
            placement=[
                PlacementHint(role="r", dx=0, dy=0, orientation="R0"),
                PlacementHint(role="c", dx=96, dy=0, orientation="R0"),
            ],
        )
    ]
    pinned = matches_to_pinned_hints(matches)
    assert pinned == {"R1": (0, 0, "R0"), "C1": (96, 0, "R0")}


def test_naive_placer_honors_pinned_hint() -> None:
    """Pinned components in the hint must end up at exactly those coordinates."""
    from wirewright.placers.grid_naive import NaivePlacer

    sch = _rc_lowpass_schematic()
    placed = NaivePlacer().place(sch, hints={"pinned": {"R1": (0, 0, "R0"), "C1": (96, 0, "R0")}})
    r1 = placed.component_by_ref("R1")
    c1 = placed.component_by_ref("C1")
    assert (r1.x, r1.y) == (0, 0)
    assert (c1.x, c1.y) == (96, 0)
