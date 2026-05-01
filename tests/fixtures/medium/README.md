# Medium fixtures

9–20 components. Light transistor count, at most one subcircuit, recognizable
TB-303 functional blocks. This tier is where the placer choice starts to
matter. HOLA should produce something compact and symmetric; the naive
fallback should at least produce a valid `.asc`.

## Contents

| File | Components | Notes |
|------|-----------:|-------|
| `tb303-vca.net` | 10 | VCA — uses `BA662` subcircuit |
| `tb303-vcf-ota.net` | 10 | VCF OTA core — uses `BA662` |
| `tb303-power.net` | 11 | Power-supply section (D, L, C) |
| `tb303-vcf-ladder.net` | 11 | VCF ladder (R/C/V/E) |
| `tb303-vcf-constant-peak.net` | 12 | Constant-peak VCF variant |
| `tb303-vcf-resonance.net` | 12 | Resonance section |
| `tb303-vco-saw-cliptop.net` | 13 | VCO sawtooth top-clip |
| `tb303-vco-saw-cliptop-bottom.net` | 14 | VCO sawtooth top+bottom clip |
| `tb303-vcf-full.net` | 18 | Full VCF block |
| `tb303-envelope.net` | 20 | VCF + VCA envelope generators |

## Canonical Phase 1 round-trip target

`tb303-envelope.net` is the canonical "medium" reference. Parses cleanly
today (R/C/D/B/E only, no transistors). Hand-drawn `tb303-envelope.asc`
to be authored in LTspice during Phase 1.
