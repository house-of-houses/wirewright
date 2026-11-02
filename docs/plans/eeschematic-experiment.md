# EEschematic side experiment plan (v2)

Tracks a bounded, side-branch experiment comparing an MLLM-based placer
(EEschematic-style) against HOLA on wirewright's fixtures. Lives on
`experiment/eeschematic` branch; not merged unless it beats HOLA on a
pre-defined readability metric.

v2 incorporates adversarial review findings
(`docs/plans/eeschematic-experiment.review.md`, 2026-10-30). Changes
from v1 documented at `## Changes from v1`.

## Why now

v0.2.0 shipped. The 2026-10 research pass surfaced four 2025–2026
papers directly or adjacently attacking the schematic-placement
problem; EEschematic (arXiv 2510.17002, Oct 2025) is the closest
architectural match. Authors released MIT-licensed code at
https://github.com/eelab-dev/EEschematic. v0.2.md listed this as
"unscheduled" — now scheduling.

Question: **does an MLLM placer with a 6-idiom few-shot library beat
HOLA on a pre-defined readability metric for wirewright's analog
corpus?** If yes, Phase 4 patterns pivot. If no, HOLA stays and we have
real data to stop asking.

## Non-goals

- Replacing HOLA in core.
- Fine-tuning any model.
- Shipping in v0.3.
- Faithful reproduction of EEschematic's Gemini setup.

## Decisions (recorded after v1 review)

- **MLLM**: OpenAI GPT-5 (vision), with GPT-4o fallback. User choice
  2026-10-30.
- **First fixture**: `tests/fixtures/easy/divider.net`. Pure-R circuit,
  no transistors — a pure plumbing gate. CMOS-vs-bipolar transfer
  question doesn't apply here.
- **Blocker-1 call (CMOS→bipolar transfer)**: accept as explicit
  hypothesis. Rationale: divider gate test is transistor-free, so
  Tasks 1–9 are not blocked. Re-decide (port idioms to bipolar vs.
  add CMOS fixtures) at the first bipolar-fixture failure.
- **Blocker-2 call (determinism)**: amend `docs/specs/placer-interface.md`
  with a `deterministic: bool` class attribute. `TestAnyPlacer` skips
  the determinism assertion when `False`. Small spec change, allows
  future stochastic placers (SA, sampled, Jev-style).
- **Blocker-3 call (divider test oracle)**: no hand-drawn `.asc` exists.
  Oracle is structural: `validate_placed(result)` passes AND component
  set + net connectivity isomorphic to the parsed netlist's graph.
- **Branch**: `experiment/eeschematic` (already created). Deleted on
  failure, merged only on documented win.
- **Dependency scoping**: `openai` goes in `[dependency-groups] experiments`.
  Not in default `uv sync`.
- **Readability metric** (pre-defined, blind): structural score +
  blind A/B. See `## Readability metric` below.

## Readability metric

Pre-defined before any benchmark output is seen, to kill
confirmation-bias.

**Structural score** (computed, no human in loop):
- `wire_length_total` — sum of Manhattan distances; lower better
- `wire_crossings` — count of orthogonal wire–wire crossings; lower better
- `bbox_overlaps` — count via existing `validate_placed`; must be zero
- `canvas_area` — bounding box area; lower better

Reported per fixture. No single scalar — a Pareto comparison vs. HOLA.

**Blind A/B** (human verdict, blinded):
- `tools/benchmark_eeschematic.py` renders HOLA and LLM outputs as PNG
  labelled only "A" and "B" randomly per fixture, mapping stored in a
  separate `_cmp/<fixture>/label.json` the reviewer doesn't open.
- Reviewer records preference in `_cmp/<fixture>/verdict.md` as A/B/same
  plus 1-sentence reason.
- After all 21 fixtures reviewed, labels revealed, win-rate computed.

Merge decision rules:
- LLM wins blind A/B by ≥ 60% AND Pareto-dominates on no fewer than 2
  structural metrics → merge candidate (needs separate v0.3 planning).
- Otherwise → do not merge, document findings, keep branch as reference.

## Scope (ordered tasks)

### Task 1: Branch skeleton, spec amendment, failing test

- Branch `experiment/eeschematic` already created.
- Amend `docs/specs/placer-interface.md`:
  - Add `deterministic: bool` class attribute to `Placer` base
    (default `True`).
  - Add paragraph: "A placer whose output varies for identical inputs
    MUST set `deterministic = False`. The determinism assertion in
    `TestAnyPlacer` is skipped for such placers; all other invariants
    still apply."
- Update `src/wirewright/placers/base.py`: add `deterministic: bool = True`
  attribute to `Placer`.
- Update `TestAnyPlacer` (locate the file via grep in Task 1): skip
  the determinism assertion when `cls.deterministic is False`.
- `src/wirewright/experiments/__init__.py` (empty).
- `src/wirewright/experiments/eeschematic/__init__.py` (empty).
- `tests/experiments/__init__.py` (empty).
- `tests/experiments/eeschematic/test_divider_plumbing.py` with ONE
  failing integration test marked `@pytest.mark.openai_live`:
  - Parse `tests/fixtures/easy/divider.net` via existing parser.
  - Call `EEschematicPlacer().place(schematic, hints=...)`.
  - Assert: `validate_placed(result)` passes; component set equal;
    `nx.is_isomorphic(result.net_graph, input.net_graph)`.
- Conftest in `tests/experiments/` auto-skips when `OPENAI_API_KEY` is
  unset AND when `WIREWRIGHT_RUN_LIVE_LLM=1` is unset. Both gates
  required; prevents accidental spend in CI.
- `pyproject.toml`: add `[dependency-groups] experiments = ["openai>=1.0"]`.
  Run `uv sync --group experiments` locally only. Default `uv sync` on
  master pulls nothing new.

### Task 2: `[` Prompt and format study

Read-only. Scratchpad clone at
`/private/tmp/claude-501/.../scratchpad/EEschematic/` already exists.

- Document EEschematic's JSON schema in
  `src/wirewright/experiments/eeschematic/json_format.py` as a
  `TypedDict` with a docstring citing the EEschematic MIT copyright.
- Document which of their 9 prompt files
  (`check_prompt.txt`, `connect_prompt.txt`, `connecting_prompt.txt`,
  `modify_prompt.txt`, `node_prompt.txt`, `optimise_prompt.txt`,
  `place_prompt.txt`, `wire_correction.txt`, `wire_correction_action.txt`)
  are used by placement vs. wiring, in a module-level docstring. No code
  changes to the project in this task.

### Task 3: Rendering pipeline (matplotlib, not cairosvg)

Renderer first — Task 4 depends on it. `cairosvg` dropped: needs
system libs CI doesn't have. `matplotlib` already a transitive dep
candidate; add to the `experiments` dep group explicitly if not present.

- `src/wirewright/experiments/eeschematic/render.py`:
  - `render_schematic_png(s: Schematic, out: Path) -> Path`
  - Component glyphs: use primitive shapes keyed off symbol name.
    `res` = rectangle with "R" label, `cap` = two parallel lines,
    `npn`/`pnp` = circle with arrow (direction varies), `opamp2` = triangle,
    sources = circle with symbol, `polcap` = cap with "+".
  - Rotations: R0/R90/R180/R270/M0/M90/M180/M270 applied via matplotlib
    `Affine2D`.
  - Wires: `ax.plot()` with Manhattan segments.
  - Grid: faint 16-unit grid for visual reference.
  - Pin dots at pin positions (small filled circles).
  - Deterministic PNG output (fixed figure size, dpi, random seed).
- Unit tests: render a hand-constructed 2-R schematic, assert output
  file exists, non-empty, approximately correct bbox pixel count.
- Scope reality check: matplotlib primitives for ~12 LTspice symbols is
  ~1 session. Not multi-week. If it balloons past 2 sessions, STOP and
  escalate — the plan then needs a scope rewrite.

### Task 4: Six-idiom few-shot library

Depends on Task 3.

- `src/wirewright/experiments/eeschematic/idioms/` with 6 subdirs:
  `single_cascode/`, `single_current_source/`, `diode_connected/`,
  `two_transistor_cascode/`, `differential_pair/`, `current_mirror/`.
- Each has `netlist.net` (SPICE), `positions.json` (EEschematic JSON
  schema from Task 2), `rendered.png` (produced by Task 3 renderer).
- Netlists ported from EEschematic's `netlist_to_schema/netlist/`
  (CMOS). Document in `idioms/README.md`: "These idioms are CMOS;
  wirewright's corpus is bipolar; transfer is the hypothesis under
  test."
- No bipolar porting at this stage per Blocker-1 decision.

### Task 5: OpenAI client with error → `PlacerEngineError` mapping

- `src/wirewright/experiments/eeschematic/openai_client.py`:
  - Thin wrapper around `openai.OpenAI()`.
  - `vision_call(system, user, images, model="gpt-5") -> str`
  - Catches `openai.APIStatusError` (4xx/5xx), `openai.APITimeoutError`,
    `openai.RateLimitError`, `openai.APIConnectionError`,
    `openai.BadRequestError` → re-raise as
    `wirewright.placers.base.PlacerEngineError` with original as
    `__cause__`.
  - Catches `openai.ContentFilterError` or equivalent → wrap as
    `PlacerEngineError("content filter triggered")`.
  - Retry: 3 attempts with exponential backoff on rate-limit and 5xx
    only. No retry on 4xx or content filter.
  - Logs every call with: model, prompt tokens (est), completion
    tokens, cost estimate. Appends to `_cmp/<fixture>/calls.jsonl`.
- Unit tests: mock the SDK, assert mapping for each exception class.

### Task 6: Placement VCoT loop

Depends on Tasks 2, 3, 5.

- `src/wirewright/experiments/eeschematic/agent.py`:
  - `place(schematic: Schematic, max_iters: int = 10) -> Schematic`
  - Loop:
    1. Render current state to PNG (Task 3).
    2. Call OpenAI (Task 5) with:
       - System prompt = EEschematic's `place_prompt.txt` (verbatim,
         MIT-attributed in docstring).
       - User = netlist + 6 idiom examples (JSON + PNG per Task 4)
         + current state (JSON + PNG) + "critique and refine, or
         output DONE".
    3. Parse response as JSON. On parse failure, retry once with
       repair prompt; after that raise `PlacerEngineError`.
    4. Translate response JSON → IR via `translator.py` (Task 2 writes
       the TypedDict; Task 6 writes the translator).
    5. Run `validate_placed(ir)`. On failure, treat as a `BAD` state
       and loop; log in `calls.jsonl`.
    6. Check for DONE sigil; if present and `validate_placed` passes,
       return.
    7. Hit `max_iters`? Return best-validating state so far; log
       "truncated".
- Per-fixture budget cap: $20. Enforced by summing `calls.jsonl` costs
  and raising `PlacerEngineError("budget exceeded")` when hit.

### Task 7: Wiring VCoT loop (optional for v0.3-experiment)

Depends on Task 6.

- `wire(schematic: Schematic, max_iters: int = 20) -> Schematic`
- Same structure, EEschematic's `wire_correction.txt` and
  `connecting_prompt.txt`.
- **May be skipped** if Task 6 placement output on divider has
  acceptable wiring from existing `routing/orthogonal.py`. Decision
  point at end of Task 9.
- DoD change (vs v1): Task 7 is explicitly **optional** and may close
  as "deferred, acceptable without".

### Task 8: `EEschematicPlacer` + CLI integration

- `src/wirewright/placers/eeschematic.py`:
  ```
  class EEschematicPlacer(Placer):
      name = "eeschematic"
      deterministic = False  # amended spec permits this
      def place(self, s, hints=None):
          from wirewright.experiments.eeschematic.agent import place
          return place(s)
  ```
- Register in `placers/__init__.py` always (no env flag). The flag was
  fragile (import-time read, test ordering, monkeypatch friction).
- Call-time check instead: `EEschematicPlacer.__init__` raises
  `RuntimeError` if `OPENAI_API_KEY` is unset. CLI `--placer eeschematic`
  thus fails loudly without a key, cheaply.
- `AutoPlacer` not changed. `eeschematic` is never in the auto chain.

### Task 9: Divider prove-out gate

- Integration test from Task 1 passes.
- Invocation uses `fnox exec --` to inject `OPENAI_API_KEY` from the
  macOS keychain (see `fnox.toml` and https://fnox.jdx.dev). This keeps
  the key out of shell history, out of the Claude Code transcript, and
  out of any file in the repo. One-time setup: `fnox set OPENAI_API_KEY`
  (or `pbpaste | fnox set OPENAI_API_KEY`). Then:
  - Tests: `fnox exec -- uv run pytest tests/experiments/eeschematic/ -v -s`
  - CLI: `fnox exec -- uv run wirewright render <net> --placer eeschematic -o out.asc`
- `wirewright render tests/fixtures/easy/divider.net --placer eeschematic
  -o /tmp/divider-llm.asc` end-to-end.
- Open `/tmp/divider-llm.asc` in LTspice: components placed, wires
  connected, no overlaps.
- **Decision point**:
  - PASS → go to Task 10 (full-corpus benchmark). Also decide: skip
    Task 7 wiring loop or run it.
  - FAIL (parse errors, wild coords, API failures) → stop. Document in
    `docs/notes/eeschematic-verdict.md`, delete branch.
- Gate acknowledged as a plumbing check, not a quality check (divider
  is trivial). Full quality assessment is Task 10.

### Task 10: Full-corpus benchmark + verdict

Depends on Task 9 PASS.

- `tools/benchmark_eeschematic.py`:
  - Iterate 21 fixtures (`tests/fixtures/{easy,medium,hard}/*.net`).
  - For each: run HOLA, run EEschematic (with per-fixture $20 cap).
  - Produce `_cmp/<fixture>/` with: `hola.asc`, `llm.asc`, `hola.png`,
    `llm.png`, `A.png`, `B.png` (randomized), `label.json` (hidden
    mapping), `calls.jsonl`, `structural.json` (metrics).
  - Aggregate `_cmp/benchmark.md`: per-fixture row + totals.
- User runs blind A/B review via existing `tools/review.py` extended
  to show A/B pairs only (no filenames).
- After review complete, run `tools/benchmark_eeschematic.py --reveal`
  to unseal `label.json` and compute win-rate.
- Write `docs/notes/eeschematic-verdict.md`:
  - Per-fixture: HOLA structural score, LLM structural score, blind
    verdict, cost.
  - Aggregate win-rate.
  - Merge decision per `## Readability metric` rules above.
- CHANGELOG entry under new `v0.3-experiments` section regardless of
  outcome.

## Definition of done

- Tasks 1–6, 8–10 complete.
- Task 7 complete OR explicitly marked deferred with justification.
- `docs/notes/eeschematic-verdict.md` written.
- Branch merged OR deleted, rationale in verdict doc.
- `v0.3-experiments` CHANGELOG section exists.

## Risk register

1. **GPT-5 unavailable** → fall back to GPT-4o. No plan change.
2. **Cost blowout**: raised cap from v1's $100 → $200 soft / $400 hard.
   Per-fixture cap $20. Reviewer's math: $30–$85 placement + ~$100–200
   wiring = $130–285. $200 soft covers placement-only; wiring triggers
   soft cap.
3. **CMOS→bipolar transfer fails on first non-divider fixture**: plan
   stops at Task 10, documents, offers option (b)/(c) for v0.4.
4. **Matplotlib renderer undersells schematic**: fallback is to render
   via existing `.asc` + a headless LTspice conversion (platform-fragile
   but higher fidelity). Decision at Task 3 end.
5. **MIT attribution**: EEschematic MIT text copied to
   `src/wirewright/experiments/eeschematic/LICENSE_EESCHEMATIC`. All
   files that lift prompts verbatim include the copyright notice in
   their docstring.
6. **Confirmation-bias in reviewer** addressed by blind A/B + randomized
   label mapping + locking metric before benchmark runs.

## Changes from v2 (post advisor on 2026-10-30 after T3 commit)

Rescope on advisor's four observations:

- **T4 (idioms) deferred to post-T9.** Divider is R/R/V/GND — none of the 6
  CMOS idioms fire. Critical path to the gate is translator → T5 → T6 →
  T8 → T9. If T9 fails, T4 effort is wasted. Idiom list is a prompt-builder
  parameter (empty list for divider).
- **T6 translator by ref, not by typeName.** Deep-copy the input
  ``Schematic``, lookup by ``name == ref``, set only ``x``, ``y``,
  ``orientation``. Component identity preserved by construction.
  typeName is advisory; prompt lists refs with symbols
  (``R1:res Q3:npn ...``). This dissolves the CMOS/bipolar typeName
  mismatch — the hypothesis becomes actually testable.
- **T6 uses existing router for wiring.** EEschematic's wire output is
  non-snapped ``(name, x, y)`` pairs; translating to ``Wire`` objects
  = reimplementing a router. Reuse ``routing/orthogonal.py``: model
  places → translator sets positions → existing router wires → T3
  renders → model critiques routed result. ``validate_placed`` passes
  by construction (axis-aligned, pins exact).
- **T7 (wiring loop) off default path, not just "optional".** Only
  revisit if T10 shows routing is the losing dimension in blind A/B.
- Scale constants: ``1 EEschematic unit = 16 IR units``; Y flip (negate);
  rotation string → ``R{n}``; flip ``"horizontal"`` → ``M0`` family
  (verify with a translator unit test placing ``res`` at R90).
- First live divider call runs with ``max_iters=3`` and prints per-call
  cost before raising the ceiling.
- ``uv sync`` must be invoked with ``--all-extras`` or every extra listed
  — ``--extra`` *replaces* rather than adds.

## Changes from v1 (post adversarial review)

- Blocker fixes: spec amendment task added (determinism), divider test
  oracle changed to structural, CMOS/bipolar transfer declared as
  explicit hypothesis.
- Renderer: `cairosvg` → `matplotlib` (no system libs).
- Env flag: import-time → call-time check inside placer `__init__`.
- Dep add: `uv add` → `[dependency-groups] experiments` scope.
- Error mapping: new Task 5 for OpenAI → `PlacerEngineError`.
- Readability metric: defined pre-benchmark with blind A/B + structural
  Pareto, not deferred to `tools/review.py` manual verdict.
- Cost cap raised with explicit per-fixture budget.
- Task ordering: renderer (Task 3) now precedes idioms (Task 4).
- MIT attribution tightened: copyright in each file that lifts prompts,
  not just a sibling LICENSE.

## Deferred

- Replacing HOLA regardless of outcome — separate v0.4 plan.
- Fine-tuning — premature.
- Comparison vs. Schemato — separate experiment after this one.
- SchGen relative-offset IR — too invasive; v0.4 if this experiment
  succeeds.
- Bipolar idiom port — v0.3-experiment-v2 if transfer visibly fails.
