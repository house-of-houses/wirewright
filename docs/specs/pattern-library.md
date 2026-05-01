# Spec: Analog idiom pattern library

**Status**: stable in v0.1.

## Overview

A pattern is a recognizable analog circuit idiom (differential pair, current mirror, opamp inverting feedback, RC filter section, TB-303 ladder rung) plus a layout template. The pattern matcher walks an unplaced `Schematic`, finds instances of registered patterns via subgraph isomorphism, and produces placement hints that the underlying placer respects.

## Why this matters

Generic graph placement algorithms (ELK, HOLA) do not know that a differential pair should be drawn as two transistors mirrored around a vertical axis with their emitters joined at the bottom. They will produce a topologically correct but visually wrong layout. Patterns inject domain knowledge.

This is the same architectural strategy used by commercial tools (SpiceVision PRO) and by IC physical design tools (ALIGN at UMN/TAMU/Intel).

## Template format

```yaml
name: <pattern_id>             # required, snake_case
version: <integer>             # required, bumps on layout-affecting change
description: <free text>
priority: <integer>            # higher wins on overlap; default 100

match:
  components:                  # required, ≥1; ≥2 for templates with topology
    - role: <role_name>
      symbol: <symbol_name>    # IR symbol name; matches Component.symbol
  topology:                    # required, ≥1 entry
    - <role>.<pin> == <role>.<pin>      # same-net constraint
    - <role>.<pin> != <role>.<pin>      # different-net constraint
    - <role>.<pin> == GND               # connected to ground

placement:                     # optional; pattern detected even if omitted
  <role>:
    dx: <int>                  # offset from anchor (multiple of LTSPICE_GRID = 16)
    dy: <int>                  # multiple of LTSPICE_GRID = 16
    orientation: R0|R90|R180|R270|M0|M90|M180|M270
```

The matcher returns, for each instance found, the role-to-component-ref mapping and the placement transform. The placer takes these as `hints["pinned"]` entries.

**Single-component templates** (only one role) are rejected at template-load time in v0.1: VF2 needs at least two roles to perform a meaningful subgraph isomorphism, and topology constraints involving a single role's own pins (e.g. `q.E == GND`) bypass VF2 entirely. Single-component matching by symbol-only is doable but adds complexity for limited benefit; deferred to v0.2.

## v0.1 shipping library

The matcher and template format are stable in v0.1. The shipping library is
a representative subset; the remaining templates are deferred to v0.2 once
ELK supports honoring `pinned` hints in `interactiveLayout` mode (v0.1
NaivePlacer is the only placer that honors `pinned`).

| Pattern | Description | v0.1 |
|---------|-------------|:----:|
| `rc_lowpass` | Single-pole RC LPF | ✓ |
| `rc_highpass` | Single-pole RC HPF | ✓ |
| `diff_pair_npn` | NPN differential pair, mirrored vertically | ✓ |
| `diff_pair_pnp` | PNP variant | ✓ |
| `current_mirror_npn` | NPN current mirror, base shared, one diode-connected | ✓ |
| `current_mirror_pnp` | PNP variant | ✓ |
| `common_emitter_npn` | CE stage with collector + emitter R | ✓ |

## v0.2 backlog

| Pattern | Description |
|---------|-------------|
| `diff_pair_{nmos,pmos}` | MOSFET differential pair |
| `current_mirror_{nmos,pmos}` | MOSFET current mirror |
| `cascode_{npn,nmos}` | Stacked transistor with shared base/gate |
| `common_source_nmos` | NMOS equivalent of CE stage |
| `opamp_inverting` | opamp + Rin + Rfb (needs opamp subcircuit handling) |
| `opamp_noninverting` | opamp + Rfb + Rg |
| `opamp_sallen_key_lpf` | 2-pole Sallen-Key low-pass |
| `bjt_diff_amp_full` | diff pair + tail current source + mirror load |
| `tb303_ladder_rung` | One stage of TB-303 transistor ladder filter |
| `expo_converter_2t` | 2-transistor exponential converter |

## Conflict resolution

If multiple patterns match overlapping components, the higher-priority pattern wins, and lower-priority matches involving any of those components are discarded.

## How patterns interact with placers

The matcher produces a list of `PatternMatch` objects, each containing:
- The pattern name and version.
- The role-to-component-ref mapping.
- A set of placement constraints (pinned positions, alignment groups, separation distances).

These are passed to the placer's `hints` dict. Each placer back end translates them to its native constraint vocabulary.

## What's NOT a pattern

- Ad-hoc placement preferences for one specific circuit (use a pinned-positions config file).
- Routing decisions (handled by the routing module).
- Symbol selection (handled by the parser).

## Open questions

- DSL or code? YAML is the v0.1 plan because non-engineers can write patterns. If YAML proves too limiting, we move to a Python DSL with a YAML compatibility layer.
- Pattern versioning: patterns evolve as we learn what works visually. Each pattern carries a version; circuits placed with v1 of a pattern are reproducible later by pinning the pattern version.
- Should patterns be allowed to specify symbol orientation overrides for individual components (e.g. "draw this resistor horizontally")? Probably yes.
