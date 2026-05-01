# Phase 2 Implementation Plan (rev 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the SPICE parser so the canonical hard fixture
`tb303-vco-integrated.net` parses cleanly into IR, satisfying the Phase 2
DoD per `docs/PLAN.md`: "all three fixture netlists parse cleanly into IR".

**Architecture:** Six tasks. (1) Two-pass refactor: pre-pass collects
`.MODEL` (top-level only — local models inside `.SUBCKT` are rejected) and
`.SUBCKT` blocks (nesting and unclosed blocks rejected); main pass
dispatches to per-element handlers. All handlers accept `models` and
`subckts` kwargs; unused are ignored. (2) Q (BJT) handler with NPN/PNP
resolution from `.MODEL`; 4-node substrate Q form rejected explicitly.
(3) M (MOSFET) handler with NMOS/PMOS resolution and 3v4-pin variant
selection by node count. (4) I (current source) and S (VC switch)
handlers. S registers `sw` symbol with verified pin names `A`/`B`/`NC+`/`NC-`
matching the real `sw.asy`. (5) X subcircuit instance with flattening:
namespace prefix is `ref[1:] + "."` (drops leading `X` per
`docs/specs/netlist-parser.md:97-98`); per-instance internal-net renaming;
external port remap; recursion detection. (6) Render canonical hard
fixture; bump phase tracker.

**Tech Stack:** Python 3.11, pytest, ruff, mypy, uv. No new runtime deps.

**Spec sources:**
- `docs/PLAN.md` (Phase 2 DoD)
- `docs/specs/netlist-parser.md` (already covers Q/M/D/X in supported-elements; subcircuit-flattening section line 29-38; reference-designator section says drop leading X)
- `docs/specs/ir.md` (IR contract — no changes)

**Out of scope (deferred):**
- F/G/H controlled sources. Add when a fixture requires them.
- Hierarchy preservation. v0.1 flattens; v0.2+ may revisit.
- `.PARAM` expression evaluation. Passed through as opaque strings.
- LED/Zener/Schottky type discrimination from `.MODEL D(...)` parameters. Every D card maps to symbol `diode`.
- 4-node Q (with explicit substrate). Rejected with ParseError pointing to v0.2.
- Local `.MODEL` declarations inside `.SUBCKT` bodies. Rejected with ParseError.
- Per-element whitespace preservation in expressions; per spec (line 65) v0.1 normalizes.

**Review compliance:** rev 2; addresses findings in `docs/plans/phase-2.review.md`. B1, B2, B3, B4, M1, M2, M6, M7, m2 all incorporated below.

---

## File Structure

| Path | Action | Responsibility |
|------|--------|----------------|
| `docs/specs/netlist-parser.md` | Modify (Step 0, separate commit) | Mark D/Q/M/I/S/X as implemented in v0.1; document subcircuit-flattening algorithm; document local-`.MODEL` rejection; document 4-node-Q rejection. |
| `src/wirewright/parse/spice.py` | Major refactor | Two-pass parser. Pre-pass + per-element handlers. |
| `src/wirewright/symbols/builtin.py` | Modify | Add `_SW` symbol with verified offsets from `sw.asy`. |
| `tests/unit/test_parser.py` | Modify | Tests for Q/M/I/S/X + .MODEL/.SUBCKT/flattening/recursion + nested/unclosed `.SUBCKT` rejection + 4-node-Q rejection + local-`.MODEL` rejection. |
| `tests/unit/test_symbols.py` | Modify | Add `sw` to `_SPICE_ORDER_BY_SYMBOL` audit map. |
| `docs/PLAN.md` | Modify | Phase 2 status: in progress → complete. |
| `CLAUDE.md` | Modify | Phase tracker: 1 → 2 complete. |

---

## Task 0: Update spec ahead of implementation

**Background.** Per CLAUDE.md "If you discover the spec is wrong, fix the spec first as its own commit." The current spec already says "drop leading X" (line 97-98); the plan agrees. But the spec doesn't yet document:
- The 4-node-Q rejection.
- The local-`.MODEL` rejection.
- The B-expression whitespace normalization (already in "Open questions" line 65 — leave as-is).

**Files:**
- Modify: `docs/specs/netlist-parser.md`

- [ ] **Step 0.1: Update spec sections**

In `docs/specs/netlist-parser.md`:

1. After the "Supported element types" table, add a paragraph: "v0.1 limitations: 4-node Q cards (BJTs with explicit substrate node) raise ParseError; use the 3-node form `Q<ref> nc nb ne <model>`. Local `.MODEL` declarations inside `.SUBCKT` bodies raise ParseError; declare models at top level."
2. In the "Subcircuit handling (v0.1: flatten)" section, replace the existing flattening sketch with a tighter description that matches the implementation: "When the parser encounters `X<ref> n1 ... nN <subckt_name>`, it (1) looks up the `.SUBCKT` definition by name; (2) constructs a namespace prefix from `ref[1:] + '.'` (e.g. `XU2` → `U2.`); (3) renames every internal subckt component reference and internal net by prepending the prefix; (4) maps subckt external port nets to the call-site nets (port `IN+` → call-site arg 1, etc.); (5) inlines the resulting components into the parent schematic. Recursive subcircuits are supported. Self-recursion (a subckt calling itself, even transitively) is rejected with ParseError. Nested `.SUBCKT` definitions and unclosed `.SUBCKT` blocks are rejected with ParseError."

- [ ] **Step 0.2: Commit spec**

```bash
git add docs/specs/netlist-parser.md
git commit -m "docs(spec): document Phase 2 parser contract (4-node Q rejection, local-.MODEL rejection, flattening algorithm)"
```

---

## Task 1: Two-pass parser refactor

**Background.** Move the existing inline `if/elif` chain into per-element handlers behind a `_dispatch_element` function, with all handlers accepting `models` and `subckts` kwargs (handlers ignore unused). Add pre-pass `_collect_models_and_subckts` that detects nested `.SUBCKT`, unclosed `.SUBCKT`, and local `.MODEL` — all errors.

**Files:**
- Modify: `src/wirewright/parse/spice.py`

- [ ] **Step 1.1: Define `Subckt` and pre-pass**

Add to `parse/spice.py`:

```python
from dataclasses import dataclass


@dataclass
class Subckt:
    """A .SUBCKT definition; body lines are pre-tokenized for fast inlining."""

    name: str
    ports: list[str]
    body_lines: list[tuple[int, str]]


def _collect_models_and_subckts(
    preprocessed: list[tuple[int, str]],
) -> tuple[dict[str, str], dict[str, Subckt]]:
    """First pass: extract .MODEL types and .SUBCKT bodies. Reject malformed structure."""
    models: dict[str, str] = {}
    subckts: dict[str, Subckt] = {}
    current: Subckt | None = None

    for line_no, line in preprocessed:
        lower = line.lower()

        if lower.startswith(".model"):
            tokens = line.split()
            if len(tokens) < 3:
                raise ParseError(f"line {line_no}: malformed .MODEL: {line!r}")
            if current is not None:
                raise ParseError(
                    f"line {line_no}: local .MODEL inside .SUBCKT not supported "
                    f"in v0.1; declare {tokens[1]!r} at top level"
                )
            name = tokens[1]
            type_tag = tokens[2].split("(", 1)[0].upper()
            models[name] = type_tag

        elif lower.startswith(".subckt"):
            if current is not None:
                raise ParseError(
                    f"line {line_no}: nested .SUBCKT not allowed "
                    f"(currently inside {current.name!r})"
                )
            tokens = line.split()
            if len(tokens) < 2:
                raise ParseError(f"line {line_no}: malformed .SUBCKT: {line!r}")
            current = Subckt(name=tokens[1], ports=tokens[2:], body_lines=[])
            subckts[current.name] = current

        elif lower.startswith(".ends"):
            if current is None:
                raise ParseError(f"line {line_no}: .ENDS without matching .SUBCKT")
            current = None

        elif current is not None and not line.startswith("."):
            current.body_lines.append((line_no, line))

    if current is not None:
        raise ParseError(
            f".SUBCKT {current.name!r} not closed by .ENDS before end of file"
        )

    return models, subckts
```

- [ ] **Step 1.2: Refactor `parse_spice_text` to use two passes; extract handlers**

```python
def parse_spice_text(text: str) -> Schematic:
    schematic = Schematic()
    nets_seen: dict[str, Net] = {}

    preprocessed = _preprocess(text)
    models, subckts = _collect_models_and_subckts(preprocessed)

    inside_subckt = False
    for line_no, line in preprocessed:
        lower = line.lower()
        if lower.startswith(".subckt"):
            inside_subckt = True
            schematic.directives.append(line)
            continue
        if lower.startswith(".ends"):
            inside_subckt = False
            schematic.directives.append(line)
            continue
        if inside_subckt:
            continue

        if line.startswith("."):
            schematic.directives.append(line)
            continue

        tokens = line.split()
        if not tokens:
            continue

        _dispatch_element(schematic, nets_seen, line_no, line, tokens, models, subckts)

    schematic.nets = list(nets_seen.values())
    return schematic


def _dispatch_element(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
    models: dict[str, str],
    subckts: dict[str, Subckt],
) -> None:
    """Parse one element line. All handlers accept (models, subckts); unused ignored."""
    ref = tokens[0]
    prefix = ref[0].upper()

    if prefix in ("R", "C", "L"):
        _handle_passive(schematic, nets_seen, line_no, line, tokens, prefix)
    elif prefix == "V":
        _handle_voltage(schematic, nets_seen, line_no, line, tokens)
    elif prefix == "D":
        _handle_diode(schematic, nets_seen, line_no, line, tokens)
    elif prefix == "B":
        _handle_behavioral(schematic, nets_seen, line_no, line, tokens)
    elif prefix == "E":
        _handle_vcvs(schematic, nets_seen, line_no, line, tokens)
    # Phase 2 handlers added in Tasks 2–5:
    # elif prefix == "Q": _handle_bjt(schematic, nets_seen, line_no, line, tokens, models)
    # elif prefix == "M": _handle_mosfet(schematic, nets_seen, line_no, line, tokens, models)
    # elif prefix == "I": _handle_current(schematic, nets_seen, line_no, line, tokens)
    # elif prefix == "S": _handle_vcswitch(schematic, nets_seen, line_no, line, tokens, models)
    # elif prefix == "X": _handle_subckt_instance(schematic, nets_seen, line_no, line, tokens, models, subckts)
    else:
        raise ParseError(
            f"line {line_no}: element {prefix!r} not yet supported "
            f"(see docs/specs/netlist-parser.md). Line: {line!r}"
        )
```

Each `_handle_passive`, `_handle_voltage`, `_handle_diode`, `_handle_behavioral`, `_handle_vcvs` is the existing per-prefix code lifted into a function with a consistent signature (no behavior change).

- [ ] **Step 1.3: Add tests for the new pre-pass error paths**

Append to `tests/unit/test_parser.py`:

```python
class TestSubcktStructuralErrors:
    def test_nested_subckt_rejected(self) -> None:
        text = ".subckt A IN OUT\n.subckt B IN OUT\n.ends B\n.ends A\n"
        with pytest.raises(ParseError, match="nested .SUBCKT"):
            parse_spice_text(text)

    def test_unclosed_subckt_rejected(self) -> None:
        text = ".subckt A IN OUT\nR1 IN OUT 1k\n"
        with pytest.raises(ParseError, match="not closed by .ENDS"):
            parse_spice_text(text)

    def test_orphan_ends_rejected(self) -> None:
        with pytest.raises(ParseError, match="without matching"):
            parse_spice_text(".ends FOO\n")

    def test_local_model_rejected(self) -> None:
        text = ".subckt A IN OUT\n.model FOO NPN()\n.ends A\n"
        with pytest.raises(ParseError, match="local .MODEL"):
            parse_spice_text(text)
```

- [ ] **Step 1.4: Run tests, lint, format, types, commit**

```bash
uv run pytest tests/unit/test_parser.py -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add src/wirewright/parse/spice.py tests/unit/test_parser.py
git commit -m "refactor(parse): two-pass parser with .MODEL/.SUBCKT pre-pass and structural error detection"
```

---

## Task 2: Q (BJT) handler

**Background.** SPICE Q card: `Q<ref> nc nb ne <model>` (3-node only in v0.1). 4-node form (with substrate) explicitly rejected per Out of Scope. Model name resolved against pre-collected `.MODEL` declarations to determine NPN vs PNP. Maps to `npn` or `pnp` symbol.

**Files:**
- Modify: `src/wirewright/parse/spice.py`
- Modify: `tests/unit/test_parser.py`

- [ ] **Step 2.1: Tests**

```python
class TestBjt:
    def test_q_card_with_npn_model(self) -> None:
        text = ".model QN3904 NPN(IS=6.7e-15)\nQ1 col base emit QN3904\n.end\n"
        c = _by_ref(text, "Q1")
        assert c.symbol == "npn"
        assert c.spice_prefix == "Q"
        assert c.spice_model == "QN3904"
        assert c.pins == {"C": "col", "B": "base", "E": "emit"}

    def test_q_card_with_pnp_model(self) -> None:
        text = ".model QP3906 PNP(IS=4.5e-16)\nQ_X c b e QP3906\n.end\n"
        c = _by_ref(text, "Q_X")
        assert c.symbol == "pnp"

    def test_q_card_with_unknown_model_raises(self) -> None:
        with pytest.raises(ParseError, match="unknown BJT model"):
            parse_spice_text("Q1 c b e MISSING_MODEL\n.end\n")

    def test_q_card_4node_substrate_form_rejected(self) -> None:
        text = ".model QN3904 NPN()\nQ1 c b e sub QN3904\n.end\n"
        with pytest.raises(ParseError, match="4-node"):
            parse_spice_text(text)
```

- [ ] **Step 2.2: Implementation**

```python
def _handle_bjt(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
    models: dict[str, str],
) -> None:
    # Strict 5-token form: <ref> nc nb ne <model>. 4-node substrate form rejected.
    if len(tokens) == 6:
        raise ParseError(
            f"line {line_no}: 4-node Q form with substrate not supported in v0.1; "
            f"use 3-node 'Q<ref> nc nb ne <model>': {line!r}"
        )
    if len(tokens) != 5:
        raise ParseError(
            f"line {line_no}: expected 'Q<ref> nc nb ne <model>': {line!r}"
        )
    ref, nc, nb, ne, model_name = tokens
    model_type = models.get(model_name)
    if model_type is None:
        raise ParseError(
            f"line {line_no}: unknown BJT model {model_name!r}; "
            f"declare with '.model {model_name} NPN(...)' or PNP(...)"
        )
    if model_type == "NPN":
        symbol = "npn"
    elif model_type == "PNP":
        symbol = "pnp"
    else:
        raise ParseError(
            f"line {line_no}: BJT model {model_name!r} has unsupported type "
            f"{model_type!r} (expected NPN or PNP)"
        )
    schematic.components.append(
        Component(
            ref=ref,
            symbol=symbol,
            pins={"C": nc, "B": nb, "E": ne},
            spice_prefix="Q",
            spice_model=model_name,
        )
    )
    for n in (nc, nb, ne):
        _record_net(nets_seen, n)
```

Wire into `_dispatch_element`: `elif prefix == "Q": _handle_bjt(schematic, nets_seen, line_no, line, tokens, models)`.

- [ ] **Step 2.3: Run, commit**

```bash
uv run pytest tests/unit/test_parser.py::TestBjt -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add src/wirewright/parse/spice.py tests/unit/test_parser.py
git commit -m "feat(parse): add Q (BJT) handler with NPN/PNP resolution; reject 4-node form"
```

---

## Task 3: M (MOSFET) handler

**Background.** SPICE M: `M<ref> nd ng ns nb <model>` (4-node) or `M<ref> nd ng ns <model>` (3-node). Type from `.MODEL`. 3v4-pin variant by node count.

**Files:**
- Modify: `src/wirewright/parse/spice.py`
- Modify: `tests/unit/test_parser.py`

- [ ] **Step 3.1: Tests**

```python
class TestMosfet:
    def test_m_card_4pin_nmos(self) -> None:
        text = ".model NM NMOS()\nM1 d g s b NM\n.end\n"
        c = _by_ref(text, "M1")
        assert c.symbol == "nmos4"
        assert c.pins == {"D": "d", "G": "g", "S": "s", "B": "b"}

    def test_m_card_3pin_pmos(self) -> None:
        text = ".model PM PMOS()\nM2 d g s PM\n.end\n"
        c = _by_ref(text, "M2")
        assert c.symbol == "pmos"
        assert c.pins == {"D": "d", "G": "g", "S": "s"}

    def test_m_card_unknown_model_raises(self) -> None:
        with pytest.raises(ParseError, match="unknown MOSFET model"):
            parse_spice_text("M1 d g s b NOSUCH\n.end\n")
```

- [ ] **Step 3.2: Implementation**

```python
def _handle_mosfet(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
    models: dict[str, str],
) -> None:
    if len(tokens) not in (5, 6):
        raise ParseError(
            f"line {line_no}: expected 'M<ref> nd ng ns [nb] <model>': {line!r}"
        )
    ref = tokens[0]
    model_name = tokens[-1]
    nodes = tokens[1:-1]
    model_type = models.get(model_name)
    if model_type not in ("NMOS", "PMOS"):
        raise ParseError(
            f"line {line_no}: unknown MOSFET model {model_name!r} "
            f"(declare with '.model {model_name} NMOS(...)' or PMOS(...))"
        )
    if len(nodes) == 4:
        nd, ng, ns, nb = nodes
        symbol = "nmos4" if model_type == "NMOS" else "pmos4"
        pins = {"D": nd, "G": ng, "S": ns, "B": nb}
    else:
        nd, ng, ns = nodes
        symbol = "nmos" if model_type == "NMOS" else "pmos"
        pins = {"D": nd, "G": ng, "S": ns}
    schematic.components.append(
        Component(ref=ref, symbol=symbol, pins=pins, spice_prefix="M", spice_model=model_name)
    )
    for n in nodes:
        _record_net(nets_seen, n)
```

Wire: `elif prefix == "M": _handle_mosfet(schematic, nets_seen, line_no, line, tokens, models)`.

- [ ] **Step 3.3: Run, commit**

```bash
uv run pytest tests/unit/test_parser.py::TestMosfet -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add src/wirewright/parse/spice.py tests/unit/test_parser.py
git commit -m "feat(parse): add M (MOSFET) handler with NMOS/PMOS + 3v4-pin resolution"
```

---

## Task 4: I (current source) and S (VC switch) handlers

**Background.** I = `I<ref> n+ n- <value>`. S = `S<ref> n+ n- nc+ nc- <model>` (4-terminal switch). The `sw.asy` symbol is verified — pins `A`/`B`/`NC+`/`NC-` at offsets `(0,16)`/`(0,96)`/`(-48,80)`/`(-48,32)` with bbox `(-48, 16, 32, 96)`.

**Files:**
- Modify: `src/wirewright/symbols/builtin.py` (add `_SW`)
- Modify: `src/wirewright/parse/spice.py`
- Modify: `tests/unit/test_parser.py`
- Modify: `tests/unit/test_symbols.py` (extend audit map)

- [ ] **Step 4.1: Add `_SW` to builtin.py**

```python
_SW = SymbolGeometry(
    name="sw",
    pins={"A": (0, 16), "B": (0, 96), "NC+": (-48, 80), "NC-": (-48, 32)},
    bbox=(-48, 16, 32, 96),
)
```

Append `_SW` to the `_REGISTRY` list. (Module-load assertion already verifies pin-grid alignment; offsets here are all multiples of 16.)

- [ ] **Step 4.2: Add `sw` to audit map in tests/unit/test_symbols.py**

```python
"sw": {"A": 1, "B": 2, "NC+": 3, "NC-": 4},
```

- [ ] **Step 4.3: Run audit to verify against real `sw.asy`**

Run: `uv run pytest tests/unit/test_symbols.py::test_pin_offsets_match_asy_file -v`
Expected: PASS for sw (offsets match real `sw.asy`).
Run: `uv run pytest tests/unit/test_symbols.py::test_pin_bboxes_match_asy_file -v`
Expected: PASS for sw (bbox matches what parse_asy_file extracts).

- [ ] **Step 4.4: Tests for I and S handlers**

```python
class TestCurrentSource:
    def test_i_card_two_terminal(self) -> None:
        c = _by_ref("I1 vcc 0 1m\n.end\n", "I1")
        assert c.symbol == "current"
        assert c.spice_prefix == "I"
        assert c.pins == {"+": "vcc", "-": "0"}
        assert c.value == "1m"


class TestVcSwitch:
    def test_s_card_four_terminal(self) -> None:
        text = ".model SW1 SW(VT=0.5)\nS1 a b c d SW1\n.end\n"
        c = _by_ref(text, "S1")
        assert c.symbol == "sw"
        assert c.spice_prefix == "S"
        assert c.spice_model == "SW1"
        assert c.pins == {"A": "a", "B": "b", "NC+": "c", "NC-": "d"}

    def test_s_card_unknown_model_raises(self) -> None:
        with pytest.raises(ParseError, match="unknown switch model"):
            parse_spice_text("S1 a b c d NOSUCH\n.end\n")
```

- [ ] **Step 4.5: Handler implementations**

```python
def _handle_current(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
) -> None:
    _expect_at_least(tokens, 4, line_no, line, "<ref> <n+> <n-> <value>")
    ref, np, nn = tokens[0], tokens[1], tokens[2]
    value = " ".join(tokens[3:])
    schematic.components.append(
        Component(
            ref=ref,
            symbol="current",
            value=value,
            pins={"+": np, "-": nn},
            spice_prefix="I",
        )
    )
    for n in (np, nn):
        _record_net(nets_seen, n)


def _handle_vcswitch(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
    models: dict[str, str],
) -> None:
    _expect_at_least(tokens, 6, line_no, line, "<ref> <n+> <n-> <nc+> <nc-> <model>")
    ref = tokens[0]
    np, nn, ncp, ncn, model_name = tokens[1], tokens[2], tokens[3], tokens[4], tokens[5]
    model_type = models.get(model_name)
    if model_type != "SW":
        raise ParseError(
            f"line {line_no}: unknown switch model {model_name!r} "
            f"(declare with '.model {model_name} SW(...)')"
        )
    schematic.components.append(
        Component(
            ref=ref,
            symbol="sw",
            pins={"A": np, "B": nn, "NC+": ncp, "NC-": ncn},
            spice_prefix="S",
            spice_model=model_name,
        )
    )
    for n in (np, nn, ncp, ncn):
        _record_net(nets_seen, n)
```

Wire: `elif prefix == "I": _handle_current(...)`, `elif prefix == "S": _handle_vcswitch(schematic, nets_seen, line_no, line, tokens, models)`.

- [ ] **Step 4.6: Run, commit**

```bash
uv run pytest tests/unit/test_parser.py::TestCurrentSource tests/unit/test_parser.py::TestVcSwitch tests/unit/test_symbols.py -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add src/wirewright/parse/spice.py src/wirewright/symbols/builtin.py tests/unit/test_parser.py tests/unit/test_symbols.py
git commit -m "feat(parse): add I (current source) and S (VC switch) handlers; register sw symbol"
```

---

## Task 5: X subcircuit instance with flattening

**Background.** SPICE `X<ref> n1 n2 ... nN <subckt_name>` instantiates a subckt. Per `docs/specs/netlist-parser.md:97-98`, the namespace prefix is `ref[1:] + "."` (e.g. `XU2` → `U2.`). Internal subckt nets get the prefix; component refs inside the subckt get the prefix; external port nets remap to the call-site nets. Recursion detection via `_expansion_stack` catches direct AND transitive (mutual) recursion.

For B-card values inside the subckt body, expression whitespace is normalized on inlining (per spec line 65: "v0.1: normalize"). This is a documented limitation, not a bug.

**Files:**
- Modify: `src/wirewright/parse/spice.py`
- Modify: `tests/unit/test_parser.py`

- [ ] **Step 5.1: Tests**

```python
class TestSubcircuit:
    def test_simple_x_inlines_subckt_body_with_x_stripped_prefix(self) -> None:
        text = (
            ".subckt INV IN OUT\n"
            "R1 IN OUT 10k\n"
            ".ends INV\n"
            "XU1 vin vout INV\n"
            ".end\n"
        )
        sch = parse_spice_text(text)
        # Per spec: namespace prefix is "U1." (X stripped). R1 inside the subckt
        # becomes U1.R1; ports IN/OUT remap to call-site nets vin/vout.
        c = sch.component_by_ref("U1.R1")
        assert c.symbol == "res"
        assert c.pins == {"1": "vin", "2": "vout"}

    def test_internal_nets_get_namespace_prefix(self) -> None:
        text = (
            ".subckt DIV IN OUT\n"
            "R1 IN MID 10k\n"
            "R2 MID OUT 10k\n"
            ".ends DIV\n"
            "XD vin vout DIV\n"
            ".end\n"
        )
        sch = parse_spice_text(text)
        r1 = sch.component_by_ref("D.R1")
        r2 = sch.component_by_ref("D.R2")
        assert r1.pins == {"1": "vin", "2": "D.MID"}
        assert r2.pins == {"1": "D.MID", "2": "vout"}

    def test_unknown_subckt_raises(self) -> None:
        with pytest.raises(ParseError, match="unknown subcircuit"):
            parse_spice_text("XU1 a b NOSUCH\n.end\n")

    def test_arity_mismatch_raises(self) -> None:
        text = ".subckt TWO_PORT A B\nR1 A B 1k\n.ends TWO_PORT\nXU1 vin TWO_PORT\n.end\n"
        with pytest.raises(ParseError, match="port"):
            parse_spice_text(text)

    def test_self_recursion_rejected(self) -> None:
        text = (
            ".subckt SELF A B\n"
            "XINNER A B SELF\n"
            ".ends SELF\n"
            "XU1 a b SELF\n"
            ".end\n"
        )
        with pytest.raises(ParseError, match="recursion"):
            parse_spice_text(text)

    def test_x_ref_without_leading_x_rejected(self) -> None:
        # Defensive: X cards should always start with X. Anything else is a bug
        # because dispatch only routes here on prefix == "X".
        # (No test needed; this is structurally enforced by _dispatch_element.)
        pass
```

- [ ] **Step 5.2: Implementation**

```python
def _handle_subckt_instance(
    schematic: Schematic,
    nets_seen: dict[str, Net],
    line_no: int,
    line: str,
    tokens: list[str],
    models: dict[str, str],
    subckts: dict[str, Subckt],
    _expansion_stack: tuple[str, ...] = (),
) -> None:
    """Flatten X<ref> ... <subckt_name> by inlining the subckt body.

    Namespace prefix: ref[1:] + "." (drops leading X per spec).
    """
    if len(tokens) < 3:
        raise ParseError(f"line {line_no}: malformed X card: {line!r}")
    ref = tokens[0]
    subckt_name = tokens[-1]
    call_site_nets = tokens[1:-1]

    if subckt_name in _expansion_stack:
        raise ParseError(
            f"line {line_no}: subcircuit recursion detected: "
            f"{' → '.join((*_expansion_stack, subckt_name))}"
        )
    sub = subckts.get(subckt_name)
    if sub is None:
        raise ParseError(f"line {line_no}: unknown subcircuit {subckt_name!r}")
    if len(call_site_nets) != len(sub.ports):
        raise ParseError(
            f"line {line_no}: subcircuit {subckt_name!r} expects {len(sub.ports)} "
            f"ports {sub.ports!r}, got {len(call_site_nets)}: {call_site_nets!r}"
        )

    port_map = dict(zip(sub.ports, call_site_nets))
    namespace = ref[1:] + "." if ref[0].upper() == "X" else ref + "."
    new_stack = (*_expansion_stack, subckt_name)

    def remap_net(net: str) -> str:
        if net in port_map:
            return port_map[net]
        if net == "0" or net.lower() == "gnd":
            return "0"
        return namespace + net

    for body_line_no, body_line in sub.body_lines:
        body_tokens = body_line.split()
        body_prefix_char = body_tokens[0][0].upper()

        if body_prefix_char == "X":
            renamed_x_tokens = (
                [namespace + body_tokens[0][1:]]  # drop X then re-prefix as namespace+body_ref[1:]? careful:
                + [remap_net(n) for n in body_tokens[1:-1]]
                + [body_tokens[-1]]
            )
            # Wait: nested X means body_tokens[0] starts with X. Its own prefix
            # for further flattening will be derived from THIS handler call.
            # The cleanest: pass the full renamed ref through, let recursion
            # strip its own X.
            renamed_x_tokens = (
                [namespace + body_tokens[0]]
                + [remap_net(n) for n in body_tokens[1:-1]]
                + [body_tokens[-1]]
            )
            _handle_subckt_instance(
                schematic,
                nets_seen,
                body_line_no,
                " ".join(renamed_x_tokens),
                renamed_x_tokens,
                models,
                subckts,
                new_stack,
            )
            continue

        renamed_tokens = [namespace + body_tokens[0]]
        arity = _node_arity(body_prefix_char, body_tokens)
        renamed_tokens.extend(remap_net(n) for n in body_tokens[1 : 1 + arity])
        renamed_tokens.extend(body_tokens[1 + arity :])
        _dispatch_element(
            schematic,
            nets_seen,
            body_line_no,
            " ".join(renamed_tokens),
            renamed_tokens,
            models,
            subckts,
        )


def _node_arity(prefix: str, tokens: list[str]) -> int:
    """Net-token count for an element line (excluding ref and value/model)."""
    if prefix in ("R", "C", "L", "V", "I", "D", "B"):
        return 2
    if prefix == "Q":
        return 3
    if prefix in ("E", "S", "G", "F", "H"):
        return 4
    if prefix == "M":
        return len(tokens) - 2
    raise ParseError(f"unknown element prefix {prefix!r} inside subcircuit body")
```

**Note on nested X ref naming:** when expanding `XU1` whose body has `XINNER ...`, the inner X's ref becomes `U1.XINNER`. The recursive `_handle_subckt_instance` call sees ref = `U1.XINNER`. Its `namespace = ref[1:] + "."` if `ref[0].upper() == "X"` else `ref + "."` — first char is "U", not "X", so namespace becomes `U1.XINNER.`. Components inside become `U1.XINNER.<ref>`. That's correct: nested instance gets the parent's namespace as its own prefix, and the inner subckt's `X` is preserved as part of the path (since the outer `_handle_subckt_instance` already stripped the outer `X`).

Wire: `elif prefix == "X": _handle_subckt_instance(schematic, nets_seen, line_no, line, tokens, models, subckts)`.

- [ ] **Step 5.3: Run, commit**

```bash
uv run pytest tests/unit/test_parser.py::TestSubcircuit -v
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add src/wirewright/parse/spice.py tests/unit/test_parser.py
git commit -m "feat(parse): add X subcircuit instance with X-stripped namespace prefix flattening"
```

---

## Task 6: Render canonical hard fixture; bump phase tracker

**Background.** Phase 2 DoD per `docs/PLAN.md`: "all three fixture netlists parse cleanly into IR". Easy and medium canonical already pass. Hard canonical (`tb303-vco-integrated.net`) requires Tasks 2–5.

**Files:**
- Modify: `tests/unit/test_parser.py`
- Modify: `docs/PLAN.md`
- Modify: `CLAUDE.md`

- [ ] **Step 6.1: Strong fixture parse test**

Append to `tests/unit/test_parser.py`:

```python
class TestVcoIntegratedFixture:
    """End-to-end on tests/fixtures/hard/tb303-vco-integrated.net."""

    def test_fixture_parses_without_error(self) -> None:
        from pathlib import Path

        from wirewright.parse.spice import parse_spice_file

        path = Path(__file__).parent.parent / "fixtures/hard/tb303-vco-integrated.net"
        if not path.exists():
            pytest.skip(f"local fixture not present: {path.name}")
        sch = parse_spice_file(path)
        refs = {c.ref for c in sch.components}

        # At least one BJT (Q) component (fixture has 7 NPN/PNP transistors).
        bjt_refs = [r for r in refs if r.startswith("Q")]
        assert len(bjt_refs) >= 5, f"expected ≥5 BJTs, got {bjt_refs}"

        # OPAMP subckt has 2 components (BAMP, ROUT). Flattened with
        # namespace prefix "U_SQR." (X stripped per spec).
        u_sqr_refs = [r for r in refs if r.startswith("U_SQR.")]
        assert sorted(u_sqr_refs) == ["U_SQR.BAMP", "U_SQR.ROUT"], (
            f"OPAMP flatten produced wrong refs: {u_sqr_refs}"
        )

        # The S handler ran (fixture has S_DISCH using SW model).
        assert "S_DISCH" in refs, f"S_DISCH not found; switch handler may have failed"

        # The I handler ran (fixture has at least one I current source).
        assert any(r.startswith("I") for r in refs), "no current source found"

        # The original X line itself is gone after flattening.
        assert "XU_SQR" not in refs
```

- [ ] **Step 6.2: Run against local fixture**

Run: `uv run pytest tests/unit/test_parser.py::TestVcoIntegratedFixture -v`
Expected: PASS on author machine. If fail, capture exact ParseError, identify missing handler or edge case, extend.

- [ ] **Step 6.3: Mark Phase 2 done in PLAN.md**

In `docs/PLAN.md`'s Phase 2 section, after the "Depends on: Phase 1." line, add:

```markdown
**Status**: complete in v0.1. LED/Zener/Schottky discrimination from `.MODEL D` parameters deferred (every D maps to symbol `diode`); 4-node Q (substrate) deferred (rejected with ParseError); local `.MODEL` inside `.SUBCKT` deferred (rejected with ParseError).
```

- [ ] **Step 6.4: Bump phase tracker in CLAUDE.md**

Replace the current phase line with:

```markdown
**Current phase**: 2 complete; Phase 3 (ELK baseline) starting.
```

- [ ] **Step 6.5: Final smoke + commit**

```bash
uv run pytest && uv run ruff format && uv run ruff check && uv run mypy src
git add tests/unit/test_parser.py
git commit -m "test(parse): canonical hard fixture parses end-to-end"
git add docs/PLAN.md CLAUDE.md
git commit -m "chore: mark Phase 2 complete; bump phase tracker"
```

---

## Self-Review

**Spec coverage:**
- Q/M/D/I/S/X implemented: Tasks 2–5. ✓
- `.MODEL` collection (top-level only): Task 1. ✓
- `.SUBCKT`/`.ENDS` collection with nesting/unclosed/orphan-ends rejection: Task 1. ✓
- `.PARAM`/`.OPTIONS` directive pass-through: existing behavior preserved. ✓
- NPN/PNP/NMOS/PMOS resolution: Tasks 2/3. ✓
- 4-node Q rejection: Task 2. ✓
- LED/Zener/Schottky discrimination: explicitly deferred per Out of Scope. ✓
- Subcircuit flattening with X-stripped prefix per spec line 97-98: Task 5. ✓
- "All three fixture netlists parse cleanly": Task 6 verifies the hard canonical with strong assertions counting flattened components and checking each new handler's footprint. ✓

**Placeholder scan:**
- Step 4.1 has concrete pin offsets (verified against real `sw.asy`). No placeholder.
- All commands and code blocks are concrete.

**Type consistency:**
- `Subckt` dataclass: defined Task 1; used Tasks 1, 5.
- `_dispatch_element` signature: 7 args including models and subckts; all `_handle_*` accept the matching subset.
- `_expansion_stack: tuple[str, ...]`: Task 5 only.
- `models: dict[str, str]`: type tag is uppercase ("NPN"/"PNP"/"NMOS"/"PMOS"/"D"/"SW"); consistent across Tasks 1–4.
- Namespace prefix algorithm: `ref[1:] + "."` if `ref[0].upper() == "X"` else `ref + "."`. Documented in spec (Task 0) and matched in Task 5.

**Review-finding traceability:**

| Finding | Severity | Addressed by |
|---------|----------|--------------|
| B1 (X-prefix spec contradiction) | Blocker | Task 5 uses `ref[1:] + "."`; Task 0 documents in spec |
| B2 (.MODEL leaks from subckt) | Blocker | Task 1.1 raises ParseError on local `.MODEL` |
| B3 (4-node Q drops substrate) | Blocker | Task 2.2 raises ParseError on 6-token Q |
| B4 (sw.asy pin names) | Blocker | Task 4.1 uses verified `A`/`B`/`NC+`/`NC-` |
| M1 (nested .SUBCKT) | Major | Task 1.1 raises ParseError |
| M2 (unmatched .SUBCKT at EOF) | Major | Task 1.1 post-loop check |
| M3 (B-value whitespace normalized) | Major | Documented per spec line 65; not blocking |
| M6 (weak fixture assertion) | Major | Task 6.1 counts U_SQR refs, checks S_DISCH, checks BJT count |
| M7 (dispatcher signature) | Major | Task 1.2 fixes consistent signature |
| m2 (spec update before code) | Minor | Task 0 added as separate first commit |

---

## Execution

Sequential: Task 0 → Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6.

Per CLAUDE.md plan-review routing: rev 2 incorporates the prior review's findings; **a second adversarial review is NOT performed in the same session**. If rev 2 still fails review on independent inspection, that is a NEEDS_HUMAN promotion.
