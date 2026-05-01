# Adversarial Review: Phase 1 Plan

**Verdict:** NEEDS_REWORK

## Summary

Plan is broadly competent and correctly scopes Phase 1 deliverables, but has several BLOCKER-level issues that would produce wrong behavior on first execution. Most consequential: a pin-grid invariant in Task 2 that is dead code given existing constraints, and a missing `Opamps/`-folder-prefix handler in the `.asc` parser that breaks any real LTspice file using `opamp2`.

## BLOCKER findings

### B1. No bbox audit; new bboxes can silently drift from `.asy`

Task 1 asserts new bbox values manually. The audit test only compares pin offsets, not bboxes. Task 2's new bbox-overlap invariant relies on bbox correctness. Fix: extend the audit to also compare `SymbolGeometry.bbox` against `parse_asy_file(<asy_path>).bbox`.

### B2. Task 2's per-pin grid alignment check cannot fire on real symbols

`_check_grid_alignment` already enforces `c.x % 16 == 0`. Every registered builtin pin offset is a multiple of 16. Therefore `(c.x + dx) % 16` for any `rotate_offset` result is always 0. The proposed `_check_pin_grid_alignment` is dead code; the plan's test reaches it only via monkeypatching a bogus geometry into the private `_REGISTRY`. Two fixes available:

(a) Drop invariant 7 from `validate_placed`. Update IR spec to state that pin grid alignment is guaranteed by construction once components are on-grid AND pin offsets are grid-aligned.

(b) Move the check to symbol-registration time: assert in `builtin.py`'s module body (or a unit test) that every registered `SymbolGeometry.pins` value is a multiple of `LTSPICE_GRID`.

(b) is the "real" invariant being assumed.

### B3. Wire constructor errors lose line context in parser

Step 3.4 constructs `Wire(...)` directly. If a stray non-axis-aligned WIRE appears in input, `Wire.__post_init__` raises `ValueError` instead of `AscParseError` with line number. Wrap in try/except and re-raise with line context.

### B5. `Net.is_power` is not preserved across round-trip

`_recover_nets` reconstructs `Net.is_power` as `False` always. There is no convention in `.asc` for marking a net as power. Either add a test that documents this lossy behavior, or document explicitly in the parser docstring that `is_power` is parser-side heuristic only.

### B6. "Two flags one net raises" rejects valid LTspice files

Real LTspice users hand-edit `.asc` to put redundant FLAGs of differing names on the same net (electrically wrong but tolerated by LTspice). Hard-failing means we cannot parse some real-world files. Options: (a) downgrade to first-name-wins with a warning, or (b) keep hard-fail and document the strictness in the parser spec. Pick consciously.

## MAJOR findings

### M2. `Opamps/opamp2` library-folder prefix in `.asc` is not handled

`docs/specs/asc-emitter.md:42` explicitly says `libname` includes the folder: `Opamps/opamp2`. The plan's parser tokenizes `tokens[1]` as the symbol name and looks it up in the registry where the key is `"opamp2"`, not `"Opamps/opamp2"`. So the parser cannot read any real LTspice `.asc` using `opamp2` or `opamp`. Fix: strip leading folder paths before registry lookup, OR register both forms, OR normalize at registry-lookup time.

This also affects Task 4's round-trip claim: with this gap, `IR ↔ .asc` is not symmetric.

### M3. Round-trip test sidesteps the un-flagged-net codepath

Plan acknowledges this but ships it anyway. The actual round-trip property is *connectivity isomorphism* (a bijection between original and parsed net names exists such that pin-net mappings are preserved), not name-set equality. Fix: add a fixture with at least one un-flagged internal net, then assert bijection-based connectivity equivalence.

### M4. Phase 1 DoD has a hand-drawn-fixture round-trip bullet that this plan does not satisfy

`docs/PLAN.md:34` says "ASC emitter passes round-trip on all three fixtures (parse hand-drawn `.asc` → IR → emit `.asc` → opens in LTspice with same connectivity)." Plan correctly defers this to a user-author task but bumps the phase tracker to "Phase 1 complete" anyway. Pick one:

(a) Update `docs/PLAN.md` Phase 1 DoD to mark hand-drawn-fixture round-trip as deferred (post-Phase-2 user task).
(b) Phrase the phase tracker more carefully ("Phase 1 implementation complete; hand-drawn fixtures pending").

### M5. `_resolve_asy_path` belongs in `lib_index.py`, not the test

Path resolution that searches the LTspice subfolder hierarchy belongs in the library module. Move it to `lib_index.py` as a public helper used by both the audit test AND the parser (per M2).

### M7. Round-trip does not preserve `Schematic.nets` ordering

`emit_asc` does not write net declarations; parser builds nets in pin-iteration order. Document this in the IR spec or asc-emitter spec.

### M8. Cast-after-validation footgun

Step 3.4's `cast(Orientation, orient)` after `if orient not in _VALID_ORIENTATIONS: raise` does not narrow types automatically. Use `from typing import get_args; _VALID_ORIENTATIONS: tuple[Orientation, ...] = get_args(Orientation)` and the cast becomes redundant.

## MINOR findings

- **N1**: `spice_prefix` is not preserved across round-trip for standard prefixes (emitter only writes non-standard ones). Add explicit test asserting this lossy-by-design behavior.
- **N2**: Plan silently drops unknown `SYMATTR` keys, contradicting "fail loud" project policy. Warn or collect into `Component.unknown_attrs`.
- **N3**: Plan silently drops unknown line types (e.g. `BUSTAP`). At minimum warn.
- **N4**: `_wire_lattice_points` has O(L/16) loop. Add `len(pts) > 1000` guard.
- **N5**: IR spec has two open questions; plan removes one and leaves the other. Inconsistent. Either remove both or keep both.
- **N7**: Plan uses `ruff format --check`. If author's local format diverges, check fails. Use `ruff format` (auto-apply) instead.
- **N8**: Test `test_two_resistor_asc_recovers_nets_via_connectivity` body is empty after docstring. Either delete or fix body.
- **N9**: Wires aren't normalized by endpoint order. Round-trip set comparison works only because emitter doesn't normalize. Document or normalize.

## Coverage gap check vs Phase 1 DoD

| Bullet | Covered? |
|--------|----------|
| `docs/specs/ir.md` complete and stable | ✓ Task 5 |
| `docs/specs/asc-emitter.md` complete and stable | ✓ Task 5 |
| Full IR with validation | Already done; Task 2 strengthens (with B2 caveat) |
| Accurate pin offsets for listed symbols | ✓ Task 1 (with B5b verification needed) |
| ASC emitter round-trips on all three fixtures | ✗ deferred per plan; see M4 |
| 2-resistor unit test opens in LTspice | Synthetic `.asc` produced; "opens in LTspice" is human-in-the-loop |

## Verified non-issues (initially flagged, withdrawn)

- B4 (synthetic SHEET dimensions in test fixtures): traced through; the specific fixture works.
- M1 (opamp dropped from audit map): misread; opamp is in the map.
- M6 (rotate_offset on bbox corners): math checked; correct including mirrored orientations.

## Caller breakage risk on opamp2 pin-name change (B5b)

Grep result: only the registry definition references `"opamp2"`. No callers using old pin names. Pin-name change is safe.

## What's missing that the plan should add

1. Bbox audit against `parse_asy_file` (B1).
2. Pin-offset registration-time check (B2 fix).
3. Folder-prefix handling in parser + `lib_index._resolve_asy_path` promoted to module (M2 + M5).
4. Connectivity-isomorphism round-trip test (M3).
5. PLAN.md Phase 1 DoD update OR softer phase tracker phrasing (M4).
6. `Net.is_power` round-trip behavior decision (B5).
7. Two-flags-disagree behavior decision (B6).
