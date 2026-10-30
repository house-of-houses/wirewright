# Adversarial review: eeschematic-experiment.md

Diagnosis-only. Findings only, no remediation. Severities: BLOCKER > HIGH > MEDIUM > LOW.

---

## [BLOCKER] Placer-contract violation: `place()` is required to be deterministic

Claim: `docs/specs/placer-interface.md` section "Required behavior" lists
"Deterministic: same input + same hints = same output." An LLM agent loop
calling GPT-5 vision over 1-20 iterations is non-deterministic by
construction.
Scenario: `EEschematicPlacer` registered in `placers/__init__.py` must pass
`tests/unit/test_placers.py::TestAnyPlacer` (spec: "New back ends are
added to the test parametrization automatically"). The determinism test
fails on first run; even a seed-pinned call cannot stabilise a
model-provider endpoint.
Attaches to: Task 7 (CLI integration) and the plan's silence on the
spec contract — no "Placer interface compliance" section anywhere.

## [BLOCKER] Reference `.asc` for the Task 1 test does not exist

Claim: Task 1's failing test asserts isomorphism to
`tests/fixtures/easy/divider.asc`. That file is not in the repo
(`ls tests/fixtures/easy/` → `divider.net`, `README.md`, plus three
TB-303 netlists, no `.asc`). PLAN.md line 35 confirms hand-drawn
canonical `.asc` fixtures are "DEFERRED, gated on user-author work in
LTspice GUI."
Scenario: Task 1 silently falls through to the "else" branch (compare to
the netlist's expected net graph). Any valid translation satisfies net
graph isomorphism tautologically — the test asserts nothing about
placement correctness, so Task 1 is a no-op test and the first prove-out
gate is empty.
Attaches to: Task 1 bullet 4, lines 54-57.

## [BLOCKER] Few-shot idiom corpus is CMOS; wirewright corpus is bipolar

Claim: The six EEschematic idioms (Single Cascode, Single Current Source,
Diode Connected, Two-Transistor Cascode, Differential Pair, Current
Mirror) are MOSFET-centric. Wirewright's 21 fixtures are TB-303 analog,
whose matcher library in-repo is `diff_pair_npn`, `current_mirror_pnp`,
`common_emitter_npn` — all bipolar (NPN/PNP, symbol `npn`/`pnp` with
pins B/C/E, not M with G/D/S).
Scenario: Few-shot prompts show MOSFET symbols with pin names and
topologies that do not transfer to bipolar circuits. The model is asked
to place `Q2` (NPN BJT) using examples of `M1` (NMOS) — pin
semantics differ (collector current ≠ drain, base-emitter is forward
diode, no gate capacitance intuition applies to BJT bias). The
experiment may be answering the wrong question: "does an MLLM trained
on CMOS idioms place bipolar circuits?" rather than "does an MLLM
placer beat HOLA?"
Attaches to: Task 3, lines 74-78 and the Non-goals section which does
not flag the device-family mismatch.

## [HIGH] SVG renderer is a hidden subproject, not a Task-4 bullet

Claim: Task 4 selects "lightweight SVG renderer in
`experiments/eeschematic/render.py` reading IR directly" as "simpler"
than LTspice-headless. Current symbols module (`src/wirewright/symbols/`)
holds pin offsets and bbox only — no shape vectors for the `res`
zigzag, `npn`/`pnp` glyphs, `opamp2` triangle, `cap`/`polcap`, `diode`,
inductor arcs, voltage/current source circles, flags, net labels, or
grid.
Scenario: Rendering a schematic faithfully enough for the MLLM to
critique placement requires authoring SVG primitives for every symbol
in `symbols/builtin.py` plus orientation transforms (R0/R90/R180/R270/
M0/M90/M180/M270), FLAG rendering, directive text, wire styling. This
is multi-week work. The plan treats it as a Task-4 bullet. If the
renderer is thin, the model critiques an image that misrepresents the
schematic and gives useless feedback.
Attaches to: Task 4, lines 85-93.

## [HIGH] `place()` must raise `PlacerEngineError` on engine failure; plan has no OpenAI-error mapping

Claim: Spec failure-mode table requires "Underlying engine fails (Node
bridge crash, pyhola exception) → raise `PlacerEngineError` wrapping
the original." Plan has no mention of how OpenAI client errors (rate
limit 429, server 5xx, context-length, timeout, content filter) are
caught and remapped.
Scenario: A transient 429 inside the agent loop surfaces as a plain
`openai.RateLimitError`. `AutoPlacer`'s HOLA-to-naive fallback catches
only `PlacerEngineError`, so an `EEschematicPlacer` wired into `auto`
or sitting beside it would bubble raw SDK exceptions to the CLI.
Attaches to: Task 5 ("`openai_client.py`: thin wrapper"), Task 7
(CLI integration). No "error mapping" bullet exists.

## [HIGH] `TestAnyPlacer` auto-parametrization will try to run the LLM placer in unit tests

Claim: Spec line "Every placer is tested against the same suite of
generic placement tests (`tests/unit/test_placers.py::TestAnyPlacer`).
New back ends are added to the test parametrization automatically."
Scenario: Once `EEschematicPlacer` is registered — even behind
`WIREWRIGHT_EXPERIMENTAL=1` — any test file that imports
`wirewright.placers` with that env set will pull the OpenAI client into
the unit-test suite. In CI without the env it may silently drop
coverage of the new placer; in local dev with env set it executes real
API calls during `uv run pytest`, violating the "no new deps during
unit tests" invariant and incurring cost on every test run.
Attaches to: Task 7 lines 120-123; no mention of excluding the new
placer from `TestAnyPlacer` parametrization or the mechanism to do so.

## [HIGH] IR-level validation will reject most LLM outputs; plan has no repair path

Claim: `ir.validate.validate_placed` enforces: integer coords on
`LTSPICE_GRID`, every pin absolute position on grid, no two component
bbox overlaps, every wire axis-aligned. LLM-emitted JSON positions are
unconstrained; it will produce off-grid coords, overlapping bboxes,
and diagonal wires routinely.
Scenario: The agent loop produces a candidate placement that fails
`validate_placed`. Plan does not say whether failure (a) reroutes
inside the agent as another iteration, (b) snaps/repairs silently
and loses the signal the LLM was trying to send, or (c) raises
`PlacerError`. Each path has a different cost and quality implication.
Attaches to: Task 2 (translator) and Task 5 (agent loop). The
translator unit tests cover round-trip on hand-constructed JSON — not
on realistic model output.

## [HIGH] Cost model is likely under-budgeted

Claim: Risk register #2 says "Soft cap $50 total, hard stop $100."
GPT-5 pricing is not published (as of 2026-10-30 training cutoff
knowledge; the plan author also flags "if GPT-5 isn't released" as a
risk). GPT-4o vision pricing as of 2024-05: ~$5/1M input, $15/1M
output; a vision call with 6 idiom PNGs (~1k tokens each) + current
schematic PNG + growing text context grows per-iteration.
Scenario: 21 fixtures × ~10 iterations × $0.15-$0.40 per vision call
= $30-$85 just for the placement phase. Add Task 6 wiring phase (×20
iterations). The hard stop at $100 is likely to trigger before the
corpus benchmark finishes, forcing partial results and no verdict.
Attaches to: Risk register line 171; no itemised budget table.

## [HIGH] "Beat HOLA on readability" has no defined metric

Claim: Section 10 bullet 2: "Overall: does LLM beat HOLA on the
readability metric? Yes/No/Mixed." The readability metric is nowhere
defined. `tools/review.py` is a markdown-table-filler for user
verdicts.
Scenario: Verdict day arrives. User reviews 21 side-by-side renders.
Without a predefined rubric (per-fixture scoring dimensions, aggregation
rule, tie-breaker), the merge/no-merge call is a vibe check made by
the same person who authored the plan and paid for the API — classic
confirmation bias setup. "Does it look better" after $100 is not a
decision procedure.
Attaches to: Task 10, lines 148-156; Definition of Done, lines 157-162.

## [MEDIUM] Task 3 depends on Task 4 but ships first in task order

Claim: Task 3 produces `{name}.png` per idiom; Task 3 line 82-83 says
"PNG rendering ... decision deferred to Task 4." Task 4 is the next
task.
Scenario: Executing Task 3 strictly ships without PNGs, leaving idioms
50% built. If anything goes wrong between Tasks 3 and 4 (dep problem,
cairosvg install, branch abandoned), the "complete tasks in order"
invariant produces half-materialised artifacts that neither Task 5 nor
Task 7 can consume.
Attaches to: Task 3 bullet 2, lines 82-83.

## [MEDIUM] Task 6 is "may be deferrable" but Definition of Done requires all 10 tasks complete

Claim: Task 6 line 115-116: "May be deferrable if placement alone
produces usable output on divider — decision at end of Task 5."
Definition of Done line 159: "All 10 tasks complete."
Scenario: End of Task 5 says "wiring phase deferred." Author then has
to either declare the plan incomplete (and hence DoD not met, cannot
merge/abandon) or silently re-interpret DoD. Internal contradiction.
Attaches to: Task 6 line 115, DoD line 159.

## [MEDIUM] `uv add openai` as "runtime dep for subpackage only" is not expressible

Claim: Task 1 line 51: "uv add openai — new runtime dep for this
subpackage only."
Scenario: `uv add openai` writes a project-wide runtime dependency to
`pyproject.toml` + `uv.lock`. There is no "subpackage-only" scoping in
uv; the only split is `[dependency-groups]` (dev) or `[project.optional-
dependencies]` (extras). The plan does not say which it will be. If it
lands as a plain runtime dep, every user of wirewright master
(including the AutoPlacer path) now pulls `openai` on `uv sync` — a
long-tail regression if the branch merges.
Attaches to: Task 1 bullet 3, lines 50-53; "Dependencies to add" line
185.

## [MEDIUM] `WIREWRIGHT_EXPERIMENTAL=1` import-time env check creates test ordering fragility

Claim: Task 7 line 122-123: "Register in `placers/__init__.py` behind
an env check: `WIREWRIGHT_EXPERIMENTAL=1` enables `--placer
eeschematic`." The existing `placers/__init__.py` eagerly imports and
registers `HolaPlacer`, `NaivePlacer`, `AutoPlacer` at module import.
Scenario: Import-time env reads are evaluated once per Python process.
Tests that `os.environ[...] = ...` after import see no effect without
`importlib.reload(wirewright.placers)`. Any test using `monkeypatch.
setenv` picks up stale state. The registry contents become
test-ordering-dependent. Also: AutoPlacer's "try HOLA first" chain
(auto.py line 32-37) is wired in at import time and makes no mention
of ever delegating to `eeschematic` — the env flag only affects the
registry dictionary, not auto fallback.
Attaches to: Task 7, lines 118-124.

## [MEDIUM] `cairosvg` is not a pure-pip install on macOS

Claim: Task 4 line 93: "SVG → PNG via `cairosvg` (new dev dep,
pre-approved per AGENTS.md)."
Scenario: `cairosvg` requires system libraries (`libcairo`, `libffi`,
`libpango`, `libgdk-pixbuf`) that are not pulled by `uv sync`. On
macOS this is a `brew install cairo pango gdk-pixbuf libffi` step. CI
on `ubuntu-latest` needs `apt-get install libcairo2 libpango-1.0-0
libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info` or
the import fails. Plan treats this as a pip-level dep.
Attaches to: Task 4 line 93; "Dependencies to add" line 187.

## [MEDIUM] Divider as the Task-9 gate under-screens

Claim: Task 9 line 143: "Visual inspection ... decision point:
proceed to full-corpus benchmark or stop."
Scenario: Divider is 2 resistors, 1 voltage source, 1 ground — trivial
topology. Any coherent JSON output translates to a valid placement.
A model that passes divider can still catastrophically fail on
medium/hard TB-303 fixtures (opamps, cascaded transistors, feedback
loops). The gate screens out worst-case failures (model emits garbage)
but not the common-case failures the experiment actually needs to
decide on. Divider is a sanity-check masquerading as a prove-out.
Attaches to: Task 9, lines 141-146.

## [MEDIUM] "v0.3-experiments" CHANGELOG section is pre-committed with no planning doc update

Claim: DoD line 162: "CHANGELOG entry under v0.3-experiments regardless
of outcome." Current `docs/PLAN.md` and CLAUDE.md "Phase tracker"
show v0.2.0 ready for tag; no v0.3 section exists.
Scenario: Experiment branch adds a CHANGELOG header for an unplanned
version. Merge back to master drags the v0.3-experiments label into
history even if the experiment is abandoned, forcing either a rename
or a dangling header.
Attaches to: Definition of Done line 162.

## [LOW] Confirmation-bias risk in Task 10 review

Claim: Task 10 line 152: "User reviews output in `_cmp/` with existing
`tools/review.py`."
Scenario: The user authored the plan, chose GPT-5, and funded the API
spend. Side-by-side open rendering of `.asc` files in LTspice (same
tool, same look) with filename-labelled columns primes the reviewer to
rationalise sunk cost. No blind-labelling step is specified.
Attaches to: Task 10 lines 148-156.

## [LOW] Risk register claim "MIT permits [prompt reuse] with attribution" is loose

Claim: Risk register #5 line 179-181: "EEschematic is MIT; we can port
prompts and JSON schema with attribution."
Scenario: MIT applies to the repo contents as a whole. Prompt text in
source files is covered; JSON schema (data shape) is not copyrightable
on its own. The plan's `LICENSES/EEschematic-MIT.txt` under
`experiments/eeschematic/` is correct practice but imprecise — the
copyright notice must be preserved on substantial code portions, not
just stored in a sibling file. Minor compliance risk at merge time.
Attaches to: Risk register lines 179-181.

## [LOW] Non-mutation requirement vs. agent-loop state

Claim: Spec: "Pure: must not mutate the input Schematic. Returns a new
one."
Scenario: An agent that holds growing conversation history across
iterations is pure w.r.t. the input Schematic but not w.r.t. provider
state (model may be rate-limited by prior calls, response may differ
based on provider-side caching). Plan should state whether the
"pure" contract is interpreted as input-only (fine) or extends to
side-effect-free (impossible with network).
Attaches to: Task 5, lines 95-109; spec interpretation absent.

---

## Verdict

The plan has three independent blockers:

1. The deterministic-output contract in `placer-interface.md` structurally
   excludes an LLM placer; no adaptation path discussed.
2. Task 1's test oracle (`divider.asc`) does not exist in the repo, so
   the "failing test first" step collapses to a trivial no-op.
3. The six few-shot idioms are CMOS but the entire wirewright corpus is
   bipolar — the experiment may be unable to transfer by construction.

Each is author-fixable but each requires a planning-level decision
(amend the spec; author `divider.asc`; port idioms to bipolar OR
accept transfer learning as a bet-explicit) before the plan can
execute without rework mid-stream. The HIGH findings (SVG renderer
scope, OpenAI error mapping, TestAnyPlacer auto-pickup, IR validation
rejection, cost under-budget, undefined readability metric) each
threaten mid-run abandonment on their own.

**VERDICT: NEEDS HUMAN**

The CMOS-vs-bipolar idiom mismatch (BLOCKER #3) is not a planning
oversight the author can patch alone — it is a fundamental assumption
about whether this experiment can answer the question it poses on
this corpus. The user needs to decide: (a) accept the transfer-learning
bet explicitly as part of the experiment's hypothesis, (b) authorise
porting the six idioms to bipolar before Task 3 (changes scope
materially), or (c) switch corpora. The determinism-contract conflict
(BLOCKER #1) similarly needs a user-level call on amending the
`Placer` spec vs. isolating `EEschematicPlacer` outside the registry.
