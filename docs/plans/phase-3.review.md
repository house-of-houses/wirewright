# Adversarial Review: Phase 3 Plan

**Verdict:** NEEDS_REWORK

## BLOCKER

### B1. With `portConstraints: FIXED_SIDE`, ELK picks port positions; pins won't align

Bridge defaults to `FIXED_SIDE`. Plan emits ports with only `port.side` and no x/y, so ELK chooses each port's position along the side. The wires will land at ELK-chosen port positions, NOT our pin offsets — wires float near symbols without touching pins.

**Fix:** Switch to `portConstraints: FIXED_POS` and emit explicit per-port `x`/`y` (relative to node top-left = bbox top-left). For pin offset `(px, py)` in symbol coords and bbox `(x_min, y_min, x_max, y_max)`, port within-node coordinates are `(px - x_min, py - y_min)`.

(Coordinate translation `sx = node.x - bbox[0], sy = node.y - bbox[1]` is actually correct — reviewer's trace had an off-by-bbox; the formula compensates for symbol origin vs bbox origin.)

## MAJOR

### M1. `_port_side` returns SOUTH for every MOSFET gate

Trace for nmos gate at `(0, 80)`, bbox `(0, 0, 48, 96)`: WEST branch second condition `|px-cx|=24 > |py-cy|=32` is false → falls through. NORTH check `py=80 < cy=48` false. Returns SOUTH. Wrong.

**Fix:** Closest-edge rule: `min(d_west, d_east, d_north, d_south)` where `d_w = px - x_min`, etc.

### M3. Pairwise edges produce O(N²) routes per net

A 5-pin net → 4 edges all anchored to first port → ELK routes 4 separate wires. Use hyper-edges: one ELK edge with multiple `sources` and `targets`. Same code complexity.

### M5. ELK `spacing.nodeNode = 40` is not grid-aligned; snap may produce overlap

ELK in pixel-units; 40 / 16 = 2.5 grid units. After `snap_to_grid`, two adjacent nodes may end up touching/overlapping, failing `validate_placed`. Bump spacing to `64` (4 grid units).

## SHOULD-FIX

### S1. CI doesn't install Node; e2e test silently skipped

Add `actions/setup-node@v4` + `npm install` step in `.github/workflows/ci.yml`.

### S2. CLI render check is too weak

Plan asserts only "exit 0 and non-empty file." Add round-trip via `parse_asc_text` to verify connectivity isomorphism preservation.

### S3. `routing/orthogonal.py` exists as a stub, not missing

Plan says "Create"; should be "Replace". Cosmetic.

### S4. Subprocess timeout uncaught

Wrap `subprocess.run` to convert `TimeoutExpired` to `PlacerEngineError`.

### S6. ELK port-side property name may need fully-qualified form

May need `"org.eclipse.elk.port.side"` instead of `"port.side"`. Verify in Task 1 smoke.

## NIT

### N3. `_connect_wires_to_pins` misnomer

Body only filters zero-length wires. Rename to `_strip_zero_length_wires`.
