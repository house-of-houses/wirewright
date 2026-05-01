# Spec: Analog idiom pattern library

**Status**: stub. Will be drafted properly in Phase 5.

## Overview

A pattern is a recognizable analog circuit idiom (differential pair, current mirror, opamp inverting feedback, RC filter section, TB-303 ladder rung) plus a layout template. The pattern matcher walks an unplaced `Schematic`, finds instances of registered patterns via subgraph isomorphism, and produces placement hints that the underlying placer respects.

## Why this matters

Generic graph placement algorithms (ELK, HOLA) do not know that a differential pair should be drawn as two transistors mirrored around a vertical axis with their emitters joined at the bottom. They will produce a topologically correct but visually wrong layout. Patterns inject domain knowledge.

This is the same architectural strategy used by commercial tools (SpiceVision PRO) and by IC physical design tools (ALIGN at UMN/TAMU/Intel).

## Template format

(Sketch only. Will be finalized in Phase 5.)

```yaml
name: diff_pair_npn
description: NPN differential pair with shared emitter
match:
  components:
    - {role: q1, symbol: npn}
    - {role: q2, symbol: npn}
  topology:
    - q1.E == q2.E       # shared emitter node
    - q1.B != q2.B       # different bases
    - q1.C != q2.C       # different collectors
placement:
  q1: {dx: 0,  dy: 0,  orientation: R0}
  q2: {dx: 80, dy: 0,  orientation: M0}   # mirrored about vertical axis
priority: 100            # higher priority patterns match first
```

The matcher returns, for each instance found, the role-to-component-ref mapping and the placement transform. The placer takes these as `hints["pinned"]` entries.

## Initial library (Phase 5 deliverable)

| Pattern | Description |
|---------|-------------|
| `diff_pair_{npn,pnp,nmos,pmos}` | Differential pair, mirrored vertically |
| `current_mirror_{npn,pnp,nmos,pmos}` | Current mirror, gate/base shared |
| `cascode_{npn,nmos}` | Stacked transistor with shared base/gate |
| `common_emitter_npn` | CE stage with collector load |
| `common_source_nmos` | Equivalent for FETs |
| `rc_lowpass` | Single-pole RC LPF |
| `rc_highpass` | Single-pole RC HPF |
| `opamp_inverting` | Standard opamp + Rin + Rfb |
| `opamp_noninverting` | Standard opamp + Rfb + Rg |
| `opamp_sallen_key_lpf` | 2-pole Sallen-Key low-pass |
| `tb303_ladder_rung` | One stage of the TB-303 transistor ladder filter |
| `expo_converter_2t` | 2-transistor exponential converter |
| `bjt_diff_amp_full` | Full diff amp: pair + tail current source + mirror load |

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
