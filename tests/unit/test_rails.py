"""Tests for the power/ground rail synthesis helper."""

from __future__ import annotations

from wirewright.ir.model import Component, Net, Schematic
from wirewright.routing.rails import emit_power_ground_rails


def _two_resistor_with_ground() -> Schematic:
    """R1, R2 in series. R2 pin 2 grounded. Both resistors placed."""
    return Schematic(
        components=[
            Component(
                ref="R1",
                symbol="res",
                pins={"1": "vin", "2": "n1"},
                x=64,
                y=64,
                orientation="R0",
            ),
            Component(
                ref="R2",
                symbol="res",
                pins={"1": "n1", "2": "0"},
                x=256,
                y=64,
                orientation="R0",
            ),
        ],
        nets=[Net("vin"), Net("n1"), Net("0", is_ground=True)],
    )


def test_emit_rails_for_ground_only() -> None:
    sch = _two_resistor_with_ground()
    _wires, flags = emit_power_ground_rails(sch)

    # Exactly one ground FLAG at the rail's terminus.
    ground_flags = [f for f in flags if f.net == "0"]
    assert len(ground_flags) == 1


def test_emit_rails_no_components_returns_empty() -> None:
    sch = Schematic(components=[], nets=[Net("0", is_ground=True)])
    wires, flags = emit_power_ground_rails(sch)
    assert wires == []
    assert flags == []


def test_emit_rails_no_ground_or_power_returns_empty() -> None:
    sch = Schematic(
        components=[
            Component(
                ref="R1",
                symbol="res",
                pins={"1": "a", "2": "b"},
                x=64,
                y=64,
                orientation="R0",
            ),
        ],
        nets=[Net("a"), Net("b")],
    )
    wires, flags = emit_power_ground_rails(sch)
    assert wires == []
    assert flags == []


def test_cluster_by_x_groups_within_gap_threshold() -> None:
    from wirewright.routing.rails import _cluster_by_x

    # Pins at x=10, 20, 100. Gap 10 between first two (within threshold);
    # gap 80 to the third (above threshold).
    clusters = _cluster_by_x([(10, 0), (20, 0), (100, 0)], gap_threshold=64)
    assert len(clusters) == 2
    assert sorted(p[0] for p in clusters[0]) == [10, 20]
    assert [p[0] for p in clusters[1]] == [100]


def test_cluster_by_x_singletons_are_their_own_clusters() -> None:
    from wirewright.routing.rails import _cluster_by_x

    clusters = _cluster_by_x([(0, 0), (1000, 0), (2000, 0)], gap_threshold=64)
    assert len(clusters) == 3
    assert all(len(c) == 1 for c in clusters)


def test_clustered_mode_singleton_drops_flag_in_rail_band_with_stub() -> None:
    """Singleton clusters get a stub up to the rail band + a FLAG; no
    horizontal rail segment is drawn (no neighbor to share it with)."""
    sch = Schematic(
        components=[
            Component(
                ref="R1",
                symbol="res",
                pins={"1": "vcc", "2": "out"},
                x=64,
                y=64,
                orientation="R0",
            ),
            # Far-away R2 also on vcc — far enough to be its own cluster.
            Component(
                ref="R2",
                symbol="res",
                pins={"1": "vcc", "2": "out2"},
                x=2048,
                y=64,
                orientation="R0",
            ),
        ],
        nets=[Net("vcc", is_power=True), Net("out"), Net("out2")],
    )
    wires, flags = emit_power_ground_rails(sch, mode="clustered")
    vcc_flags = [f for f in flags if f.net == "vcc"]
    assert len(vcc_flags) == 2  # one per singleton cluster
    # All vcc flags sit ABOVE the component bodies (in the rail band).
    assert all(f.y < 64 for f in vcc_flags)
    # Stubs are vertical (x1 == x2). No horizontal rail segments for singletons.
    horizontals = [w for w in wires if w.y1 == w.y2]
    assert horizontals == []


def test_clustered_mode_two_close_pins_share_one_rail() -> None:
    sch = Schematic(
        components=[
            Component(
                ref="R1",
                symbol="res",
                pins={"1": "vcc", "2": "a"},
                x=64,
                y=64,
                orientation="R0",
            ),
            Component(
                ref="R2",
                symbol="res",
                pins={"1": "vcc", "2": "b"},
                x=128,
                y=64,
                orientation="R0",
            ),
        ],
        nets=[Net("vcc", is_power=True), Net("a"), Net("b")],
    )
    wires, flags = emit_power_ground_rails(sch, mode="clustered")
    vcc_flags = [f for f in flags if f.net == "vcc"]
    assert len(vcc_flags) == 1  # single cluster -> single FLAG
    # Two stubs (one per pin) plus one horizontal rail segment.
    assert len(wires) >= 3


def test_scattered_mode_emits_one_flag_per_pin_no_rails() -> None:
    sch = Schematic(
        components=[
            Component(
                ref="R1",
                symbol="res",
                pins={"1": "vcc", "2": "a"},
                x=64,
                y=64,
                orientation="R0",
            ),
            Component(
                ref="R2",
                symbol="res",
                pins={"1": "vcc", "2": "b"},
                x=128,
                y=64,
                orientation="R0",
            ),
        ],
        nets=[Net("vcc", is_power=True), Net("a"), Net("b")],
    )
    wires, flags = emit_power_ground_rails(sch, mode="scattered")
    vcc_flags = [f for f in flags if f.net == "vcc"]
    assert len(vcc_flags) == 2
    assert wires == []


def test_global_mode_preserves_legacy_single_rail() -> None:
    sch = Schematic(
        components=[
            Component(
                ref="R1",
                symbol="res",
                pins={"1": "vcc", "2": "a"},
                x=64,
                y=64,
                orientation="R0",
            ),
            Component(
                ref="R2",
                symbol="res",
                pins={"1": "vcc", "2": "b"},
                x=2048,
                y=64,
                orientation="R0",
            ),
        ],
        nets=[Net("vcc", is_power=True), Net("a"), Net("b")],
    )
    _wires, flags = emit_power_ground_rails(sch, mode="global")
    vcc_flags = [f for f in flags if f.net == "vcc"]
    # Global mode collapses everything to one rail with one FLAG, regardless
    # of how far apart the pins are.
    assert len(vcc_flags) == 1


def test_emit_rails_for_power_net() -> None:
    sch = Schematic(
        components=[
            Component(
                ref="R1",
                symbol="res",
                pins={"1": "vcc", "2": "out"},
                x=64,
                y=64,
                orientation="R0",
            ),
            Component(
                ref="R2",
                symbol="res",
                pins={"1": "vcc", "2": "out2"},
                x=256,
                y=64,
                orientation="R0",
            ),
        ],
        nets=[Net("vcc", is_power=True), Net("out"), Net("out2")],
    )
    # In clustered mode the two pins are too far apart to share a rail,
    # so each gets its own FLAG above the component bodies.
    _wires, flags = emit_power_ground_rails(sch)
    vcc_flags = [f for f in flags if f.net == "vcc"]
    assert len(vcc_flags) == 2
    # Power flags should be ABOVE the components (smaller y in canvas coords).
    assert all(f.y < 64 for f in vcc_flags)
