# Hard fixtures

>20 components OR heavy transistor count OR multiple subcircuits. Dense
feedback, requires symmetry to be readable. This tier is where pattern
recognition (Phase 4) becomes essential — bare HOLA produces something
legible-but-not-great; a working ladder-rung or diff-amp pattern
template should make a visible difference.

## Contents

| File | Components | Notes |
|------|-----------:|-------|
| `tb303-vco-expo-tempsweep-uncompensated.net` | 19 | 5 BJTs, expo converter |
| `tb303-vco-expo-tempsweep-ptc1k.net` | 20 | + PTC compensation |
| `tb303-vco-expo-tempsweep-ptc2k.net` | 20 | + PTC compensation (2k) |
| `tb303-accent.net` | 21 | accent shaper, uses `BA662` |
| `tb303-vco-expo.net` | 21 | 6 BJTs, full expo converter |
| `tb303-voice-chain.net` | 22 | full voice chain, uses `BA662` |
| `tb303-vco-integrated.net` | 38 | full VCO, 7 BJTs + `OPAMP` subcircuit + S/I/D |

## Canonical Phase 1 round-trip target

`tb303-vco-integrated.net` is the canonical "hard" reference. Requires
Phase 2 parser work (Q, M, I, X, S) before it parses; hand-drawn
`tb303-vco-integrated.asc` to be authored in LTspice once Phase 2 lands.
