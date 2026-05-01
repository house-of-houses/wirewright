# Adversarial Review: Phase 2 Plan

**Verdict:** NEEDS_REWORK

## BLOCKER findings

### B1. Spec contradiction on flattened reference designators

`docs/specs/netlist-parser.md:97-98` says: "For flattened subcircuits, references are prefixed with the call-site reference (e.g. `XU2.R5` becomes `U2.R5`)." Plan keeps the leading `X` (`XU1.R1`). Pick one and align.

**Resolution: match the spec — drop the leading X.** Namespace prefix becomes `ref[1:] + "."` (e.g. `XU_SQR` → `U_SQR.`, `XINNER` → `INNER.`).

### B2. `.MODEL` declarations inside `.SUBCKT` leak into global model table

Pre-pass processes `.model` regardless of `current_subckt`. Any `.model` inside a subckt becomes globally visible. Reject with ParseError pointing to v0.2.

### B3. Q-card with substrate node (4 nodes) silently drops the substrate

Plan binds `tokens[3]` as `ne` and `tokens[-1]` as model — silently discards `tokens[4]` if present. Reject 4-node Q with explicit ParseError.

### B4. `_handle_vcswitch` pin names disagree with real `sw.asy`

Real `sw.asy` declares pin names `A`, `B`, `NC+`, `NC-` (not `+`, `-`, `P`, `N`). Use the real names. Verified offsets:
- `A = (0, 16)` (SpiceOrder 1)
- `B = (0, 96)` (SpiceOrder 2)
- `NC+ = (-48, 80)` (SpiceOrder 3)
- `NC- = (-48, 32)` (SpiceOrder 4)
- bbox: `(-48, 16, 32, 96)`

## MAJOR findings

### M1. Nested `.SUBCKT` blocks silently mis-parsed

Pre-pass `current_subckt` is single-valued; nesting overwrites. Reject with ParseError.

### M2. Unmatched `.SUBCKT` at EOF silently accepted

Pre-pass can exit with `current_subckt` non-None. Add post-pass check.

### M3. B-card value whitespace normalized when inlined via subckt

`body_line.split()` + `" ".join(...)` collapses internal whitespace in expressions. Per `docs/specs/netlist-parser.md:65` ("v0.1: normalize"), this is in spec — document and proceed.

### M6. Task 6 assertion too weak to detect silent flattening failure

Strengthen: count `U_SQR.*` refs (must be 2 per OPAMP body), and assert `S_DISCH` is present to verify S handler.

### M7. Dispatcher signature ambiguity

Pick one approach. Resolution: every `_handle_*` accepts `models` and `subckts` kwargs; handlers ignore unused.

## MINOR findings

### m2. Spec update should commit before code, per CLAUDE.md

The Phase 2 spec changes are documentation-only (mark D/Q/M/I/S/X implemented). Move to Step 0 before implementation begins.

### Recon results
- OPAMP subckt body in canonical hard fixture: 2 components (`BAMP`, `ROUT`). Flattened: `U_SQR.BAMP`, `U_SQR.ROUT`.
- `sw.asy` pin offsets verified above (B4).
- `.SUBCKT OPAMP IN+ IN- VDD VSS OUT` → port arity 5. `XU_SQR RAMP SQR_THRESH VDD VSS SQR_RAW OPAMP` provides 5 nets (matches).
