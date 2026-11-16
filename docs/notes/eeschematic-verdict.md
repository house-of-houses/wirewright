# EEschematic experiment verdict

**Status**: paused pending wirewright rails fix. Branch
`experiment/eeschematic` retained as a reference artifact.
**Decision date**: 2026-11-16.
**Decision author**: Gert (with Claude Code assistance).
**Plan**: [`docs/plans/eeschematic-experiment.md`](../plans/eeschematic-experiment.md).

## Question the experiment set out to answer

> Does an MLLM placer with a 6-idiom few-shot library beat HOLA on a
> pre-defined readability metric for wirewright's analog corpus?

## What got built

T1–T6, T8 shipped on `experiment/eeschematic`. T4 (idiom library) and
T7 (wiring VCoT loop) deferred per advisor after the harness revealed
they weren't on the critical path to a signal. T9 (divider prove-out)
passed. T10 (full-corpus benchmark) blocked by the rails finding below.

Branch state: 14 commits ahead of master, 222 tests + 1 live-skipped
when it was paused. All lint + types clean.

## What the runs showed

### Divider — passed (2026-11-02, re-verified 2026-11-16)

- 2 API calls, $0.02 total under `reasoning_effort="low"`
- VCoT loop engaged: iter 0 produced a valid-but-ugly mixed-orientation
  layout, iter 1 saw the render and emitted all-R0 placement
- `check_wires_induce_exact_nets(strict=True)` passed
- Output visually readable, textbook-series style (V1 left,
  R1+R2 stacked right, long clean wires)
- Not as compact as HOLA's triangle layout, but electrically correct

### `tb303-vco-saw-cliptop` — blocked by signal-net router limits

14-component fixture with one PNP transistor, VDD+VSS supplies, a
voltage-controlled switch, and an op-amp subcircuit.

Three bugs surfaced, in order:

1. **Translator silently skipped real VDD/VSS components** (fixed in
   commit `ffd7e78`). An earlier version of `eeschematic_json_to_ir`
   had a `_is_rail_placeholder` shortcut that skipped anything named
   VDD/VSS/GND, under the assumption those were EEschematic's standalone
   decoration instances. But wirewright's SPICE parser creates REAL
   voltage-source components with those refs. Regression test at
   `test_translate_places_real_vdd_voltage_source`.

2. **`emit_power_ground_rails` shorts stacked rails on shared x columns**
   (fixed on master in commit `d6758c8`). When the model places VDD
   and VSS at the same x, three rail flags stacked vertically:
   `VSS@(x, -912)`, `VDD@(x, -848)`, `GND@(x, 992)`. The vertical wire
   from a VDD pin up to its rail passed through the VSS rail's
   position. Fixed by pre-planning all rail-flag positions and routing
   stubs via `route_avoiding(..., pin_obstacles=...)` with other-rail
   flags as point obstacles. Recovered 2 of 4 HOLA-shorted fixtures
   including this one — HOLA now ships clean output here.

3. **Signal-net router can't find short-free paths on dense placements**
   (NOT fixed; the actual remaining blocker). After the rails fix, the
   LLM run on this fixture still shorts — but now on signal nets
   (RAMP ↔ TRIG), not rails. The LLM places Q_CLAMP's emitter (RAMP)
   and collector (TRIG) in positions where `route_avoiding`'s candidate
   set (2 L + 4 Z around obstacle extremes) can't find a corner that
   doesn't land on another net's pin. Same bug class as HOLA's remaining
   2 broken fixtures (`-cliptop-bottom`, `-vco-integrated`). Needs a
   stronger router with more candidate paths (jogs, multi-segment
   detours) OR placement-density changes that keep pin configurations
   routable.

### VCoT loop verdict

The loop *works*. On the catastrophic iter-0 output (all 6 nets
fused), iter 1 improved to just the 3-way rail short — the model fixed
the signal-net shorts based on the structural findings fed as text in
the critique prompt. Iters 2 and 3 then ping-ponged because the
remaining short isn't the model's fault — rails are added by wirewright
after placement, so the model can't route around them.

Total experiment spend: $0.21.

## Finding — HOLA has the same rails bug on 4 of 21 fixtures

Discovered as a side-effect of landing the wire-connectivity oracle on
master (warn-only mode). HOLA silently ships shorted schematics on:

- `medium/tb303-envelope.net`
- `medium/tb303-vco-saw-cliptop.net`
- `medium/tb303-vco-saw-cliptop-bottom.net`
- `hard/tb303-vco-integrated.net`

`validate_placed` logs a warning on each render. The LLM experiment's
strict check surfaces the same bug as a hard error. See invariant 9 in
[`docs/specs/ir.md`](../specs/ir.md).

## Side-effects that landed on master

Three master-worthy improvements composed as a side-effect of the
experiment:

- **Wire-connectivity oracle** —
  `ir.validate.check_wires_induce_exact_nets(sch, strict=False)`.
  Union-find over pin positions + wire endpoints + wire-interior
  crossings. `validate_placed` logs warnings; strict callers raise.
  Catches pin-coincident L-bend corners and rail-wire-through-pin shorts
  that `validate_placed` previously missed.
- **Pin-aware routing** —
  `routing.orthogonal.route_avoiding(..., pin_obstacles=...)`. Pin
  positions of other nets score as path-preference penalties (strictly
  above bbox crossings). Z-detour candidates now trigger on pin
  obstacles alone, not just bbox obstacles. HOLA and `NaivePlacer` both
  pass other-net pins now.
- **Invariant 9 in `docs/specs/ir.md`** — documents the no-shorts
  invariant with the warn/strict split.

## Verdict

The experiment answered its question partially:

- **For single-rail circuits (divider)**: the MLLM approach is viable.
  Output is electrically correct, visually readable, costs pennies, and
  the VCoT loop self-corrects on obvious problems.
- **For multi-rail circuits (every real TB-303 fixture)**: the approach
  is blocked by a pre-existing wirewright rails bug, not by model
  capability. The model cannot route around rails it does not control.

**No merge to master.** The experiment branch is retained as a
reference artifact for revisiting after the rails bug is fixed. The
three side-effect improvements above already landed on master.

## Next steps

1. ~~**`fix/rails-collision` on master**~~ — DONE in commit `d6758c8`.
   Recovered `tb303-envelope` and `tb303-vco-saw-cliptop` from the
   known-shorts list.
2. **Signal-net router improvements** — the real remaining blocker.
   Needed for BOTH:
   - HOLA's last 2 broken fixtures (`-cliptop-bottom`, `-vco-integrated`)
   - The EEschematic experiment on any non-trivial fixture
   Options: (a) add jog / multi-segment candidates to `route_avoiding`
   beyond the current 2 L + 4 Z set; (b) implement a proper grid-based
   A\* router for the obstacle-dense case; (c) teach placers to leave
   more routing slack around dense pin clusters.
3. **After router work lands**: rebase `experiment/eeschematic` on new
   master, re-run `tb303-vco-saw-cliptop` to confirm. If yes, run T10
   full-corpus benchmark.
4. **If T10 shows win**: Phase 4 pattern work pivots to MLLM-driven
   placement. If it shows loss: delete the branch and document the
   verdict in `CHANGELOG.md` under v0.3.
