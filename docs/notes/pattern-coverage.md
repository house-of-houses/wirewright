# Pattern coverage — v0.1

## What ships

7 templates in `src/wirewright/patterns/library/`. All have unit tests in
`tests/unit/test_patterns.py`.

| Template | Components | Topology | Test |
|----------|-----------:|----------|------|
| `rc_lowpass` | 2 | R series, C to GND | `test_rc_lowpass_match` |
| `rc_highpass` | 2 | C series, R to GND | `test_rc_highpass_match` |
| `diff_pair_npn` | 2 | Two NPN, shared E | `test_diff_pair_npn_match` |
| `diff_pair_pnp` | 2 | Two PNP, shared E | (covered by symmetry) |
| `current_mirror_npn` | 2 | NPN diode-connected + base-shared | `test_current_mirror_npn_match` |
| `current_mirror_pnp` | 2 | PNP variant | (same logic; verified via test_diff_pair_pnp pattern symmetry) |
| `common_emitter_npn` | 3 | NPN with collector R + emitter R to GND | `test_common_emitter_match` |

## Integration

- `--use-patterns` flag on `wirewright render` runs the matcher and feeds
  `pinned` hints to the placer.
- **Only `NaivePlacer` honors `pinned` in v0.1** (matched components go to
  their canonical positions; remaining components fill grid around them).
- ELK and HOLA do not honor `pinned` in v0.1; using `--use-patterns
  --placer elk` is a no-op for placement.

## v0.2 backlog (per `docs/specs/pattern-library.md`)

| Template | Reason deferred |
|----------|-----------------|
| `diff_pair_nmos` / `diff_pair_pmos` | MOSFET-specific; mechanical clones once needed |
| `current_mirror_nmos` / `current_mirror_pmos` | Same |
| `cascode_npn` / `cascode_nmos` | Multi-component stack; novel topology |
| `common_source_nmos` | NMOS analog of common_emitter_npn |
| `opamp_inverting` / `opamp_noninverting` | Needs opamp subcircuit recognition (Phase 2 flattens, but matched as bare opamp symbol vs flattened internals — design call) |
| `opamp_sallen_key_lpf` | Multi-component active filter |
| `bjt_diff_amp_full` | Composite of diff pair + tail current source + mirror load |
| `tb303_ladder_rung` | TB-303-specific; the headline "hard" idiom |
| `expo_converter_2t` | 2-transistor expo with thermistor or PTC |

## v0.2 follow-ups beyond template authoring

- ELK pinned-hint support via `org.eclipse.elk.layered.crossingMinimization.semiInteractive` or two-pass layout.
- HOLA pinned-hint support (currently HOLA has no pinning API exposed in `hola_graph`).
- Pattern conflict resolution beyond simple priority + overlap rejection.
- Multi-instance template variations (e.g. a single template that matches both NPN and PNP via parameterization).
- Single-component templates with topology constraints (currently rejected at template-load time).
