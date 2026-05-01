"""Tests for the YAML template loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from wirewright.patterns.template import (
    TemplateError,
    _parse_topology_line,
    load_default_library,
    load_template,
)

_RC_LP_YAML = """\
name: rc_lowpass_test
version: 1
description: First-order RC low-pass filter
priority: 100
match:
  components:
    - {role: r, symbol: res}
    - {role: c, symbol: cap}
  topology:
    - r.2 == c.1
    - c.2 == GND
placement:
  r:
    dx: 0
    dy: 0
    orientation: R0
  c:
    dx: 96
    dy: 0
    orientation: R0
"""


def test_load_template_parses_components(tmp_path: Path) -> None:
    p = tmp_path / "rc.yaml"
    p.write_text(_RC_LP_YAML)
    t = load_template(p)
    assert t.name == "rc_lowpass_test"
    assert {c.role for c in t.components} == {"r", "c"}
    assert next(c for c in t.components if c.role == "r").symbol == "res"


def test_load_template_parses_topology(tmp_path: Path) -> None:
    p = tmp_path / "rc.yaml"
    p.write_text(_RC_LP_YAML)
    t = load_template(p)
    assert len(t.topology) == 2
    same = next(c for c in t.topology if c.kind == "same")
    assert same.a == ("r", "2")
    assert same.b == ("c", "1")
    ground = next(c for c in t.topology if c.kind == "ground")
    assert ground.a == ("c", "2")


def test_load_template_parses_placement(tmp_path: Path) -> None:
    p = tmp_path / "rc.yaml"
    p.write_text(_RC_LP_YAML)
    t = load_template(p)
    assert len(t.placement) == 2
    assert {h.role for h in t.placement} == {"r", "c"}


def test_topology_unrecognized_raises() -> None:
    with pytest.raises(TemplateError, match="unrecognized"):
        _parse_topology_line("r.1 ~~ c.2")


def test_single_component_template_rejected(tmp_path: Path) -> None:
    p = tmp_path / "single.yaml"
    p.write_text(
        "name: single\nversion: 1\nmatch:\n  components:\n    - {role: q, symbol: npn}\n  topology:\n    - q.E == GND\n"
    )
    with pytest.raises(TemplateError, match="single-component"):
        load_template(p)


def test_off_grid_placement_rejected(tmp_path: Path) -> None:
    p = tmp_path / "offgrid.yaml"
    p.write_text(
        "name: badgrid\nversion: 1\nmatch:\n"
        "  components:\n    - {role: a, symbol: res}\n    - {role: b, symbol: res}\n"
        "  topology:\n    - a.2 == b.1\n"
        "placement:\n  a: {dx: 0, dy: 0, orientation: R0}\n"
        "  b: {dx: 24, dy: 0, orientation: R0}\n"
    )
    with pytest.raises(TemplateError, match="grid"):
        load_template(p)


def test_invalid_orientation_rejected(tmp_path: Path) -> None:
    p = tmp_path / "badorient.yaml"
    p.write_text(
        "name: badorient\nversion: 1\nmatch:\n"
        "  components:\n    - {role: a, symbol: res}\n    - {role: b, symbol: res}\n"
        "  topology:\n    - a.2 == b.1\n"
        "placement:\n  a: {dx: 0, dy: 0, orientation: R0}\n"
        "  b: {dx: 96, dy: 0, orientation: R45}\n"
    )
    with pytest.raises(TemplateError, match="orientation"):
        load_template(p)


def test_load_default_library_finds_v01_templates() -> None:
    templates = load_default_library()
    names = {t.name for t in templates}
    expected = {
        "rc_lowpass",
        "rc_highpass",
        "diff_pair_npn",
        "diff_pair_pnp",
        "current_mirror_npn",
        "current_mirror_pnp",
        "common_emitter_npn",
    }
    assert expected.issubset(names), f"missing: {expected - names}"
