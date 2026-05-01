# Easy fixtures

≤8 components, no discrete transistors, no subcircuits. Smoke tests for the
pipeline. If a placer can't render these readably, something is fundamentally
wrong.

## Contents

| File | Components | Element types |
|------|-----------:|---------------|
| `divider.net` | 3 | R, V |
| `tb303-slide.net` | 5 | R, C, V |
| `tb303-vcf-8hz-peak.net` | 8 | R, V, E, B |
| `tb303-vco-full.net` | 8 | B, R, V (behavioral, no transistors) |

## Canonical Phase 1 round-trip target

`divider.net` is the canonical "easy" reference. A hand-drawn `divider.asc`
authored in LTspice during Phase 1 is the visual round-trip target (parse
hand-drawn `.asc` → IR → emit `.asc` → diff structurally).
