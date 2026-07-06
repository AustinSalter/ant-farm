# Survey Pipeline Implementation Plan (plan 2 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build ant-farm's survey pipeline — the `workflows/survey.js` orchestrator, the seven survey agent definitions (plus a mechanical clerk), phases 0–7, schema-forced agent outputs, script-enforced CONCLUDE gates, R/E/C bands, and the persona-swap counterfactual.

**Architecture:** The workflow script is thin orchestration: it dispatches schema-forced agents and branches on JSON returned by a `python -m antfarm` CLI. Every deterministic decision — emission→event conversion, entailment merge, CONCLUDE gates, tripwire firing, view materialization — lives in the tested Python package; the JS never computes anything it could get wrong. Agents emit pydantic-validated "emission" records (no ids, no vantage, no `verified` flag); the CLI stamps vantage and timestamps, computes content-hash ids, and appends append-only events. Workflow scripts have no filesystem access, so a low-effort **clerk** subagent executes exact CLI commands and returns stdout.

**Tech Stack:** Python ≥3.12, uv, pydantic v2, chromadb, networkx (all existing); Claude Code dynamic workflows (JS, `agent()`/`parallel()`/`pipeline()`); node only for CI syntax-checking.

**Spec:** `docs/specs/2026-07-03-ant-farm-design.md` (spec §N references below). Plan 1 (corpus-core) is merged; its modules are consumed as-is.

## Global Constraints

- **Locked decisions from plan 1 (do not revisit):** entailment threshold **0.67** (never 0.85); `answered_challengers` requires a **live** answerer; the reducer has exactly **one** post-fold canonicalization pass; chroma vantage metadata uses **per-member boolean keys** (`family_gpt: True`); chroma collections always get `embedding_function=None`; `EmbeddingMatcher` uses the numpy bucket index.
- **Schema-forcing at the `agent()` call** (spec §3, §4.1): every survey agent gets `schema:` from pydantic `model_json_schema()` exports passed into the workflow via `args.schemas`. Malformed records cannot enter the corpus; atoms that fail the self-containedness validator are **rejected and reported**, never silently repaired.
- **Agents never stamp their own provenance:** emissions carry no `id`, no `vantage`, no `ts`, no `verified`. The CLI stamps vantage from orchestrator-supplied flags; `verified: true` is only ever produced by the verification floor (Phase 4) or the sentinel's evidence path.
- **Blinding rules (spec §3, non-negotiable):** blind-critic reads a farm's `turns.jsonl` as an authorless third-party document and retrieves from the **well**; scouts read only their own farm dir and retrieve from the **view**; farms are evidence-blind to each other until stitch (the chroma store is rebuilt only at Phase 7, so mid-run retrieval hits the *prior* run's view); no pass iterates to consensus.
- **CONCLUDE gates are script-enforced** (spec §5 Phase 2): ≥1 HIGH-severity falsification trigger on record, no un-sublated undercutters against the farm's atoms, degeneration ledger clean (2 consecutive novel-content-free patches force ELEVATE/CONCEDE). The gate lives in Python (`antfarm.gates`), not in agent judgment and not in JS.
- **Confidence:** R and C are ordinal bands (`low|med|high`) self-reported per compress; **E is derived from the corpus** (diagnosticity counts in this plan; rarefaction slope added in plan 3). Never a composite, never presented as probabilities (spec §7).
- **Event filenames sort chronologically** within a run dir: `p0-sentinel`, `p1-framing`, `p2-farm{F}-r{NN}`, `p3-farm{F}-r{NN}`, `p4-verify`, `p5-stitch`, `p6-{farm}`, `p7-materialize` (rounds zero-padded to 2). Run dirs are `r0001`-style (plan 1 constraint).
- **Corpus directory layout** (one corpus dir per question): `runs/` (event JSONL only — `read_events` rglobs `*.jsonl`, so **nothing else** under `runs/` may use that extension; sidecars are `.json`), `farms/<run>/<farm>/` (turns.jsonl, ledger.jsonl, triggers.jsonl, critiques/, meta.json, outcome.json), `chroma/`, `vault/`, `exports/<run>/<farm>/` (keel export), `emb-cache.json`, `question.json`.
- **Model families:** the workflow runtime exposes only Anthropic tiers; `vantage.family` records the tier (`opus`/`sonnet`/`haiku`), rotated across farms via `agent()`'s `model` option. Cross-provider routing is out of scope (spec §12); whether tier+persona diversity yields n_eff > 1.5 is plan 3's measurement (spec §13.2).
- Tests marked `@pytest.mark.eval` use real embedding models; default `pytest` excludes them. Deterministic tests and the pipeline smoke script use `ANTFARM_EMBED=hash` (no downloads). The offline embedding is `hash_embed`: 256-dim hashed word unigrams+bigrams — 32-dim char-trigram vectors were too dense (nearly all English sentence pairs exceeded the 0.67 entailment threshold, so distinct fixture atoms spuriously merged; amended 2026-07-05 during execution).
- Run `uv run ruff check src tests` (line length 100) and `uv run mypy src` before every commit; both must pass clean.
- Use `X | None`, never `Optional[X]`. Shared test builders live in `tests/helpers.py`; never re-declare them.
- New test modules must be added to the `disallow_untyped_defs = false` mypy override list in `pyproject.toml` (mypy cannot wildcard bare module names) — Task 1 adds them all at once.

---

### Task 1: Emission schemas — the agent-facing output contract

Every survey agent's output is one of these models. `export_schemas()` is what the invoking session passes into the workflow as `args.schemas`.

**Files:**
- Create: `src/antfarm/emission.py`
- Modify: `pyproject.toml` (mypy override list)
- Test: `tests/test_emission.py`

**Interfaces:**
- Consumes: `LedgerEntry` from `antfarm.transcript` (fields: `trigger, change, novel_content`)
- Produces: type aliases `Band = Literal["low","med","high"]`, `Severity = Literal["low","med","high"]`, `FarmDecision = Literal["CONTINUE","CONCLUDE","ELEVATE","CONCEDE"]`; models `AtomEmission(type, text, strength, diagnosticity)`, `EdgeEmission(src, dst, rel, warrant)`, `AtomBatch(atoms, edges)`, `TriggerEmission(text, severity)`, `SublationItem(critique, disposition, response)`, `ScoutRoundOutput`, `CritiqueFinding`, `CritiqueReport`, `Dissolve`, `ZwickyDimension`, `ZwickyCell`, `RivalHypothesis`, `FramingOutput`, `HoleFinderOutput`, `ACHCell`, `StitchInvestigation`, `BasinPosition`, `StitchOutput`, `SentinelCheck`, `SentinelReport`, `VerificationResult`, `RegeneratedTurn`, `PersonaSwapOutput`, `CuratorOutput`; registry `SCHEMAS: dict[str, type[BaseModel]]`; `export_schemas() -> dict[str, dict]`

- [ ] **Step 1: Add future test modules to the mypy override**

In `pyproject.toml`, replace the first `[[tool.mypy.overrides]]` module list with:

```toml
[[tool.mypy.overrides]]
module = [
    "test_schema", "test_events", "test_reduce", "test_cluster", "test_graph",
    "test_stores", "test_transcript", "test_counterfactual", "test_render",
    "test_emission", "test_harvest", "test_gates", "test_tripwires", "test_analysis",
    "test_farm", "test_brief", "test_cli", "test_materialize", "test_agents",
    "helpers", "conftest",
]
disallow_untyped_defs = false
```

- [ ] **Step 2: Write the failing test**

`tests/test_emission.py`:

```python
import pytest
from pydantic import ValidationError

from antfarm.emission import (
    AtomEmission,
    Dissolve,
    EdgeEmission,
    FramingOutput,
    RivalHypothesis,
    ScoutRoundOutput,
    export_schemas,
)

SCOUT_KW = dict(
    expansion="Grid storage constrains solar buildout because batteries lag panels.",
    atoms=[AtomEmission(type="claim", text="Grid storage lags panel deployment by years.")],
    compressed_state="Thesis: storage, not panels, is the binding constraint.",
    confidence_r="med", confidence_c="high",
)


def test_atom_emission_has_no_provenance_fields():
    fields = set(AtomEmission.model_fields)
    assert fields == {"type", "text", "strength", "diagnosticity"}
    # no id, no vantage, no ts, no verified - the orchestrator stamps those


def test_atom_emission_rejects_crux_and_tripwire_types():
    with pytest.raises(ValidationError):
        AtomEmission(type="crux", text="x")  # cruxes are computed, never emitted
    with pytest.raises(ValidationError):
        AtomEmission(type="tripwire", text="x")  # tripwires come from triggers


def test_supports_edge_requires_warrant_at_emission():
    with pytest.raises(ValidationError):
        EdgeEmission(src="a", dst="b", rel="supports")
    ok = EdgeEmission(src="a", dst="b", rel="supports", warrant="cost curves license this")
    assert ok.warrant


def test_edge_emission_excludes_scored_against():
    with pytest.raises(ValidationError):
        EdgeEmission(src="a", dst="b", rel="scored_against")  # stitcher ACH cells only


def test_scout_round_decision_literals():
    out = ScoutRoundOutput(decision="CONTINUE", **SCOUT_KW)
    assert out.decision == "CONTINUE"
    with pytest.raises(ValidationError):
        ScoutRoundOutput(decision="HALT", **SCOUT_KW)


def test_concede_requires_died_because():
    with pytest.raises(ValidationError):
        ScoutRoundOutput(decision="CONCEDE", **SCOUT_KW)
    ok = ScoutRoundOutput(decision="CONCEDE", died_because="rival explains the evidence",
                          **SCOUT_KW)
    assert ok.died_because


def test_dissolve_requires_replacement_question():
    with pytest.raises(ValidationError):
        Dissolve(dissolved=True, diagnosis="fake binary")
    ok = Dissolve(dissolved=True, diagnosis="fake binary",
                  replacement_question="Which storage mix serves peak load cheapest?")
    assert ok.replacement_question


FRAMING_KW = dict(
    stasis="quality", altitude="market-level, 5-year horizon",
    reference_class="infrastructure cost-decline theses",
    base_rate="roughly half of such theses survive a decade",
    zwicky_dimensions=[], incoherent_cells=[],
)


def test_framing_requires_rivals_with_null():
    with pytest.raises(ValidationError, match="2-4 rival"):
        FramingOutput(dissolve=Dissolve(), rivals=[RivalHypothesis(text="only one")],
                      **FRAMING_KW)
    with pytest.raises(ValidationError, match="null"):
        FramingOutput(dissolve=Dissolve(),
                      rivals=[RivalHypothesis(text="a"), RivalHypothesis(text="b")],
                      **FRAMING_KW)
    ok = FramingOutput(dissolve=Dissolve(), rivals=[
        RivalHypothesis(text="Storage is the binding constraint."),
        RivalHypothesis(text="No single constraint dominates.", is_null=True),
    ], **FRAMING_KW)
    assert len(ok.rivals) == 2


def test_dissolved_framing_needs_no_rivals():
    ok = FramingOutput(
        dissolve=Dissolve(dissolved=True, diagnosis="presupposes a single constraint",
                          replacement_question="What limits solar in each region?"),
        rivals=[], **FRAMING_KW)
    assert ok.dissolve.dissolved


def test_export_schemas_covers_every_agent_output():
    schemas = export_schemas()
    assert set(schemas) == {
        "scout_round", "critique_report", "framing", "hole_finder", "stitch",
        "sentinel_report", "verification_result", "persona_swap", "curator",
        "atom_batch",
    }
    assert schemas["scout_round"]["properties"]["decision"]["enum"] == [
        "CONTINUE", "CONCLUDE", "ELEVATE", "CONCEDE"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_emission.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'antfarm.emission'`

- [ ] **Step 4: Write minimal implementation**

`src/antfarm/emission.py`:

```python
"""Agent-facing output models. Everything a survey agent returns is one of these,
schema-forced at the agent() call via export_schemas(). Emissions carry no id,
no vantage, no ts, no verified flag - antfarm.harvest stamps provenance."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from antfarm.transcript import LedgerEntry

Band = Literal["low", "med", "high"]
Severity = Literal["low", "med", "high"]
FarmDecision = Literal["CONTINUE", "CONCLUDE", "ELEVATE", "CONCEDE"]
EmittableType = Literal["claim", "evidence", "tension", "hypothesis", "source"]
EmittableRel = Literal[
    "supports", "rebuts", "undercuts", "qualifies", "bridges", "depends_on", "supersedes"
]


class AtomEmission(BaseModel):
    type: EmittableType
    text: str
    strength: int | None = Field(default=None, ge=1, le=5)
    diagnosticity: Literal["high", "med", "none"] | None = None


class EdgeEmission(BaseModel):
    """Endpoints are either an existing corpus id (c-8f3a...) or the exact text
    of an atom in the same emission batch."""

    src: str
    dst: str
    rel: EmittableRel
    warrant: str | None = None

    @model_validator(mode="after")
    def _supports_needs_warrant(self) -> "EdgeEmission":
        if self.rel == "supports" and not self.warrant:
            raise ValueError("supports edges require a warrant (Toulmin, spec §4.1)")
        return self


class AtomBatch(BaseModel):
    atoms: list[AtomEmission]
    edges: list[EdgeEmission] = Field(default_factory=list)


class TriggerEmission(BaseModel):
    """A falsification trigger: a self-contained condition that would falsify
    the farm's thesis, graded by severity (Popper/Mayo, spec §7)."""

    text: str
    severity: Severity


class SublationItem(BaseModel):
    critique: str
    disposition: Literal["accepted", "rebutted", "qualified"]
    response: str


class ScoutRoundOutput(BaseModel):
    sublation: list[SublationItem] = Field(default_factory=list)
    expansion: str
    atoms: list[AtomEmission]
    edges: list[EdgeEmission] = Field(default_factory=list)
    falsification_triggers: list[TriggerEmission] = Field(default_factory=list)
    compressed_state: str
    confidence_r: Band
    confidence_c: Band
    ledger_entry: LedgerEntry | None = None
    decision: FarmDecision
    died_because: str | None = None

    @model_validator(mode="after")
    def _concede_needs_died_because(self) -> "ScoutRoundOutput":
        if self.decision == "CONCEDE" and not self.died_because:
            raise ValueError("CONCEDE requires died_because")
        return self


class CritiqueFinding(BaseModel):
    target_text: str
    kind: Literal["warrant_probe", "premortem", "contradiction", "evidence_challenge"]
    classification: Literal["rebutting", "undercutting"]
    severity: Severity
    text: str


class CritiqueReport(BaseModel):
    findings: list[CritiqueFinding]
    premortem: str
    summary: str


class Dissolve(BaseModel):
    dissolved: bool = False
    diagnosis: str | None = None
    replacement_question: str | None = None

    @model_validator(mode="after")
    def _dissolved_needs_replacement(self) -> "Dissolve":
        if self.dissolved and not self.replacement_question:
            raise ValueError("DISSOLVE requires a replacement question (spec §5 Phase 1)")
        return self


class ZwickyDimension(BaseModel):
    name: str
    values: list[str]


class ZwickyCell(BaseModel):
    assignment: dict[str, str]
    reason: str


class RivalHypothesis(BaseModel):
    text: str
    is_null: bool = False
    warm_started: bool = False


class FramingOutput(BaseModel):
    stasis: Literal["fact", "definition", "quality", "policy"]
    altitude: str
    dissolve: Dissolve
    reference_class: str
    base_rate: str
    zwicky_dimensions: list[ZwickyDimension]
    incoherent_cells: list[ZwickyCell] = Field(default_factory=list)
    rivals: list[RivalHypothesis] = Field(default_factory=list)

    @model_validator(mode="after")
    def _rivals_unless_dissolved(self) -> "FramingOutput":
        if self.dissolve.dissolved:
            return self
        if not 2 <= len(self.rivals) <= 4:
            raise ValueError("framing requires 2-4 rival hypotheses (spec §5 Phase 1)")
        if not any(r.is_null for r in self.rivals):
            raise ValueError("rivals must include the null hypothesis")
        return self


class HoleFinderOutput(BaseModel):
    candidate: str | None
    reasoning: str


class ACHCell(BaseModel):
    evidence_text: str
    hypothesis_text: str
    consistency: Literal["consistent", "inconsistent", "neutral"]


class StitchInvestigation(BaseModel):
    farms: list[str]
    disagreement: str
    resolution: str
    atoms: list[AtomEmission] = Field(default_factory=list)
    edges: list[EdgeEmission] = Field(default_factory=list)


class BasinPosition(BaseModel):
    hypothesis_text: str
    condition: str | None = None


class StitchOutput(BaseModel):
    ach: list[ACHCell]
    investigations: list[StitchInvestigation] = Field(default_factory=list)
    declaration_kind: Literal["basin", "frontier"]
    declaration_summary: str
    positions: list[BasinPosition]
    dissolve: Dissolve


class SentinelCheck(BaseModel):
    tripwire_id: str
    fired: bool
    evidence: str


class SentinelReport(BaseModel):
    checks: list[SentinelCheck]


class VerificationResult(BaseModel):
    atom_id: str
    verified: bool
    evidence: str
    source: str | None = None


class RegeneratedTurn(BaseModel):
    phase: Literal["sublate", "expand", "compress"]
    iteration: int
    content: str


class PersonaSwapOutput(BaseModel):
    turns: list[RegeneratedTurn]


class CuratorOutput(BaseModel):
    map_markdown: str


SCHEMAS: dict[str, type[BaseModel]] = {
    "scout_round": ScoutRoundOutput,
    "critique_report": CritiqueReport,
    "framing": FramingOutput,
    "hole_finder": HoleFinderOutput,
    "stitch": StitchOutput,
    "sentinel_report": SentinelReport,
    "verification_result": VerificationResult,
    "persona_swap": PersonaSwapOutput,
    "curator": CuratorOutput,
    "atom_batch": AtomBatch,
}


def export_schemas() -> dict[str, dict]:
    return {name: model.model_json_schema() for name, model in SCHEMAS.items()}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_emission.py -v`
Expected: 10 passed

- [ ] **Step 6: Commit**

```bash
uv run ruff check src tests && uv run mypy src
git add src/antfarm/emission.py tests/test_emission.py pyproject.toml
git commit -m "feat: agent-facing emission schemas, schema-forced at agent() calls"
```

---

### Task 2: Harvest — scout emissions to events and turns

The conversion layer: emissions in, append-ready events plus transcript turns out. Rejection (not repair) for non-self-contained atoms; text-or-id reference resolution for edges.

**Files:**
- Create: `src/antfarm/harvest.py`
- Test: `tests/test_harvest.py`

**Interfaces:**
- Consumes: emission models (Task 1); `Node`, `Edge`, `Vantage`, `atom_id`, `normalize_text` from `antfarm.schema`; `node_event`, `edge_event` from `antfarm.events`; `Corpus` from `antfarm.reduce`; `Turn` from `antfarm.transcript`; `helpers.make_vantage`, `helpers.make_corpus_node`
- Produces: `HarvestResult(events: list[dict], turns: list[Turn], atom_ids: list[str], rejected: list[dict], unresolved: list[dict])` (pydantic); `resolve_ref(ref: str, batch: dict[str, AtomEmission], corpus: Corpus) -> str | None`; `batch_harvest(batch: AtomBatch, *, vantage: Vantage, corpus: Corpus, question_id: str, ts: str) -> HarvestResult`; `scout_harvest(output: ScoutRoundOutput, *, vantage: Vantage, corpus: Corpus, question_id: str, ts: str, start_turn: int) -> HarvestResult`

- [ ] **Step 1: Write the failing test**

`tests/test_harvest.py`:

```python
from helpers import make_corpus_node, make_vantage

from antfarm.emission import (
    AtomBatch,
    AtomEmission,
    EdgeEmission,
    ScoutRoundOutput,
    SublationItem,
)
from antfarm.harvest import batch_harvest, resolve_ref, scout_harvest
from antfarm.reduce import Corpus
from antfarm.schema import atom_id

V = make_vantage(farm="A", round=2)
TS = "2026-07-04T00:00:00Z"
Q = "q-1"

CLAIM = "Grid storage lags panel deployment by several years."
EVIDENCE = "California curtailed 2.4 TWh of solar generation in 2024."


def _batch(**kw):
    return AtomBatch(**kw)


def test_batch_harvest_stamps_vantage_and_computes_ids():
    result = batch_harvest(
        _batch(atoms=[AtomEmission(type="claim", text=CLAIM)]),
        vantage=V, corpus=Corpus(), question_id=Q, ts=TS)
    assert result.atom_ids == [atom_id("claim", CLAIM)]
    payload = result.events[0]["payload"]
    assert payload["vantage"]["farm"] == "A" and payload["ts"] == TS
    assert payload["verified"] is False  # emissions can never claim verification


def test_non_self_contained_atom_is_rejected_not_repaired():
    result = batch_harvest(
        _batch(atoms=[AtomEmission(type="claim", text="This proves the thesis."),
                      AtomEmission(type="claim", text=CLAIM)]),
        vantage=V, corpus=Corpus(), question_id=Q, ts=TS)
    assert len(result.atom_ids) == 1
    assert result.rejected[0]["text"] == "This proves the thesis."


def test_edges_resolve_batch_text_and_corpus_id():
    existing = make_corpus_node("Solar deployment doubled between 2020 and 2024.")
    corpus = Corpus(nodes={existing.id: existing})
    result = batch_harvest(
        _batch(atoms=[AtomEmission(type="claim", text=CLAIM),
                      AtomEmission(type="evidence", text=EVIDENCE, strength=4)],
               edges=[EdgeEmission(src=EVIDENCE, dst=CLAIM, rel="supports",
                                   warrant="curtailment evidences a storage bottleneck"),
                      EdgeEmission(src=CLAIM, dst=existing.id, rel="qualifies")]),
        vantage=V, corpus=corpus, question_id=Q, ts=TS)
    edge_events = [e for e in result.events if e["kind"] == "edge"]
    assert len(edge_events) == 2
    assert edge_events[0]["payload"]["src"] == atom_id("evidence", EVIDENCE)
    assert edge_events[1]["payload"]["dst"] == existing.id


def test_edge_to_unknown_ref_is_reported_not_written():
    result = batch_harvest(
        _batch(atoms=[AtomEmission(type="claim", text=CLAIM)],
               edges=[EdgeEmission(src=CLAIM, dst="never emitted anywhere", rel="rebuts")]),
        vantage=V, corpus=Corpus(), question_id=Q, ts=TS)
    assert not [e for e in result.events if e["kind"] == "edge"]
    assert result.unresolved == [{"src": CLAIM, "dst": "never emitted anywhere",
                                  "rel": "rebuts"}]


def test_edge_from_rejected_atom_is_unresolved():
    result = batch_harvest(
        _batch(atoms=[AtomEmission(type="claim", text="It follows trivially.")],
               edges=[EdgeEmission(src="It follows trivially.", dst=CLAIM, rel="rebuts")]),
        vantage=V, corpus=Corpus(), question_id=Q, ts=TS)
    assert result.rejected and result.unresolved


def test_resolve_ref_matches_corpus_text_exactly():
    existing = make_corpus_node("Solar deployment doubled between 2020 and 2024.")
    corpus = Corpus(nodes={existing.id: existing})
    assert resolve_ref("  solar deployment DOUBLED between 2020 and 2024. ",
                       {}, corpus) == existing.id
    assert resolve_ref("c-000000000000", {}, corpus) is None  # unknown id


SCOUT = ScoutRoundOutput(
    sublation=[SublationItem(critique="Curtailment may reflect transmission, not storage.",
                             disposition="qualified",
                             response="Qualified the thesis to storage-plus-transmission.")],
    expansion="Anomaly: curtailment rose while battery installs also rose.",
    atoms=[AtomEmission(type="claim", text=CLAIM)],
    falsification_triggers=[],
    compressed_state="Thesis: storage (with transmission) binds solar growth.",
    confidence_r="med", confidence_c="med",
    decision="CONTINUE",
)


def test_scout_harvest_builds_sublate_expand_compress_turns():
    result = scout_harvest(SCOUT, vantage=V, corpus=Corpus(), question_id=Q, ts=TS,
                           start_turn=5)
    assert [(t.turn, t.phase, t.iteration) for t in result.turns] == [
        (5, "sublate", 2), (6, "expand", 2), (7, "compress", 2)]
    assert result.turns[0].role == "assistant"
    assert "qualified" in result.turns[0].content
    assert result.turns[2].content == SCOUT.compressed_state


def test_scout_harvest_round_one_has_no_sublate_turn():
    first = SCOUT.model_copy(update={"sublation": []})
    result = scout_harvest(first, vantage=make_vantage(farm="A", round=1),
                           corpus=Corpus(), question_id=Q, ts=TS, start_turn=1)
    assert [t.phase for t in result.turns] == ["expand", "compress"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_harvest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'antfarm.harvest'`

- [ ] **Step 3: Write minimal implementation**

`src/antfarm/harvest.py`:

```python
"""Emission -> event conversion. Stamps vantage and ts, computes content-hash
ids, resolves edge references (batch text | corpus text | corpus id), rejects
non-self-contained atoms, and renders scout output into transcript turns."""

import re

from pydantic import BaseModel, Field, ValidationError

from antfarm.emission import AtomBatch, AtomEmission, EdgeEmission, ScoutRoundOutput
from antfarm.events import edge_event, node_event
from antfarm.reduce import Corpus
from antfarm.schema import Edge, Node, Vantage, atom_id, normalize_text
from antfarm.transcript import Turn

_ID_RE = re.compile(r"^[a-z]-[0-9a-f]{12}$")


class HarvestResult(BaseModel):
    events: list[dict] = Field(default_factory=list)
    turns: list[Turn] = Field(default_factory=list)
    atom_ids: list[str] = Field(default_factory=list)
    rejected: list[dict] = Field(default_factory=list)
    unresolved: list[dict] = Field(default_factory=list)


def resolve_ref(ref: str, batch: dict[str, AtomEmission], corpus: Corpus) -> str | None:
    if _ID_RE.match(ref):
        return ref if ref in corpus.nodes else None
    key = normalize_text(ref)
    if key in batch:
        emission = batch[key]
        return atom_id(emission.type, emission.text)
    for nid, node in corpus.nodes.items():
        if normalize_text(node.text) == key:
            return nid
    return None


def _convert(atoms: list[AtomEmission], edges: list[EdgeEmission], *, vantage: Vantage,
             corpus: Corpus, question_id: str, ts: str) -> HarvestResult:
    result = HarvestResult()
    accepted: dict[str, AtomEmission] = {}
    for emission in atoms:
        try:
            node = Node.create(type=emission.type, text=emission.text, vantage=vantage,
                               question_id=question_id, ts=ts,
                               strength=emission.strength,
                               diagnosticity=emission.diagnosticity)
        except ValidationError as err:
            result.rejected.append({"text": emission.text,
                                    "error": str(err.errors()[0]["msg"])})
            continue
        result.events.append(node_event(node))
        result.atom_ids.append(node.id)
        accepted[normalize_text(emission.text)] = emission
    for emission_edge in edges:
        src = resolve_ref(emission_edge.src, accepted, corpus)
        dst = resolve_ref(emission_edge.dst, accepted, corpus)
        if src is None or dst is None:
            result.unresolved.append({"src": emission_edge.src, "dst": emission_edge.dst,
                                      "rel": emission_edge.rel})
            continue
        result.events.append(edge_event(Edge(src=src, dst=dst, rel=emission_edge.rel,
                                             warrant=emission_edge.warrant,
                                             vantage=vantage, ts=ts)))
    return result


def batch_harvest(batch: AtomBatch, *, vantage: Vantage, corpus: Corpus,
                  question_id: str, ts: str) -> HarvestResult:
    return _convert(batch.atoms, batch.edges, vantage=vantage, corpus=corpus,
                    question_id=question_id, ts=ts)


def scout_harvest(output: ScoutRoundOutput, *, vantage: Vantage, corpus: Corpus,
                  question_id: str, ts: str, start_turn: int) -> HarvestResult:
    result = _convert(output.atoms, output.edges, vantage=vantage, corpus=corpus,
                      question_id=question_id, ts=ts)
    index = start_turn
    if output.sublation:
        content = "\n".join(f"[{item.disposition}] {item.critique}\n{item.response}"
                            for item in output.sublation)
        result.turns.append(Turn(turn=index, role="assistant", phase="sublate",
                                 iteration=vantage.round, content=content))
        index += 1
    result.turns.append(Turn(turn=index, role="assistant", phase="expand",
                             iteration=vantage.round, content=output.expansion))
    result.turns.append(Turn(turn=index + 1, role="assistant", phase="compress",
                             iteration=vantage.round, content=output.compressed_state))
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_harvest.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
uv run ruff check src tests && uv run mypy src
git add src/antfarm/harvest.py tests/test_harvest.py
git commit -m "feat: scout emission harvest - provenance stamping, ref resolution, turns"
```

---

### Task 3: Harvest — critique, framing, stitch, and verification conversions

**Files:**
- Modify: `src/antfarm/harvest.py` (append)
- Test: `tests/test_harvest.py` (append)

**Interfaces:**
- Consumes: `_convert`, `resolve_ref`, `HarvestResult` (Task 2); `CritiqueReport`, `FramingOutput`, `StitchOutput`, `VerificationResult` (Task 1); `edge_event`, `node_event`
- Produces: `critique_harvest(report, *, vantage, corpus, hypothesis_id: str, question_id, ts, start_turn) -> HarvestResult` (findings → claim nodes + rebuts/undercuts edges; premortem → claim + undercuts edge to the hypothesis; one `role="user", phase="critique"` turn); `framing_harvest(output, *, vantage, question_id, ts) -> tuple[HarvestResult, list[dict]]` (rivals → hypothesis nodes; second element `[{"id","text","is_null"}]`); `stitch_harvest(output, *, vantage, corpus, question_id, ts) -> HarvestResult` (investigation atoms/edges + ACH cells → `scored_against` edges with `consistency`); `verify_harvest(results: list[VerificationResult], *, corpus, vantage, ts) -> HarvestResult` (verified results → re-observation node events with `verified=True`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_harvest.py`:

```python
from antfarm.emission import (
    ACHCell,
    BasinPosition,
    CritiqueFinding,
    CritiqueReport,
    Dissolve,
    FramingOutput,
    RivalHypothesis,
    StitchInvestigation,
    StitchOutput,
    VerificationResult,
)
from antfarm.events import node_event
from antfarm.harvest import (
    critique_harvest,
    framing_harvest,
    stitch_harvest,
    verify_harvest,
)
from antfarm.reduce import reduce_events

HYP = "Storage constraints bind solar growth through 2030."
CRITIQUE_V = make_vantage(farm="A", persona="blind-critic", round=1)


def _hyp_corpus():
    hyp = make_corpus_node(HYP, type="hypothesis")
    claim = make_corpus_node(CLAIM)
    return Corpus(nodes={hyp.id: hyp, claim.id: claim}), hyp.id, claim.id


def test_critique_findings_become_claims_with_challenge_edges():
    corpus, hyp_id, claim_id = _hyp_corpus()
    report = CritiqueReport(
        findings=[CritiqueFinding(
            target_text=CLAIM, kind="warrant_probe", classification="undercutting",
            severity="high",
            text="Storage-lag statistics conflate contracted and installed capacity.")],
        premortem="The thesis failed by 2027 because interconnection queues cleared.",
        summary="One HIGH warrant probe; premortem names interconnection risk.")
    result = critique_harvest(report, vantage=CRITIQUE_V, corpus=corpus,
                              hypothesis_id=hyp_id, question_id=Q, ts=TS, start_turn=4)
    kinds = [(e["kind"], e["payload"].get("rel")) for e in result.events]
    assert ("edge", "undercuts") in kinds
    edge_payloads = [e["payload"] for e in result.events if e["kind"] == "edge"]
    assert {p["dst"] for p in edge_payloads} == {claim_id, hyp_id}
    assert [t.phase for t in result.turns] == ["critique"]
    assert result.turns[0].role == "user" and result.turns[0].turn == 4


def test_framing_rivals_become_hypothesis_nodes():
    framing = FramingOutput(
        stasis="quality", altitude="market", dissolve=Dissolve(),
        reference_class="cost-decline theses", base_rate="about half",
        zwicky_dimensions=[],
        rivals=[RivalHypothesis(text=HYP),
                RivalHypothesis(text="No single constraint binds solar growth.",
                                is_null=True)])
    result, rivals = framing_harvest(framing, vantage=make_vantage(farm="surveyor"),
                                     question_id=Q, ts=TS)
    assert [e["payload"]["type"] for e in result.events] == ["hypothesis", "hypothesis"]
    assert rivals[0] == {"id": atom_id("hypothesis", HYP), "text": HYP, "is_null": False}
    assert rivals[1]["is_null"] is True


def test_stitch_ach_cells_become_scored_against_edges():
    corpus, hyp_id, claim_id = _hyp_corpus()
    ev = make_corpus_node(EVIDENCE, type="evidence")
    corpus.nodes[ev.id] = ev
    stitch = StitchOutput(
        ach=[ACHCell(evidence_text=EVIDENCE, hypothesis_text=HYP,
                     consistency="inconsistent"),
             ACHCell(evidence_text="never recorded", hypothesis_text=HYP,
                     consistency="neutral")],
        investigations=[StitchInvestigation(
            farms=["A", "B"], disagreement="Farms disagree on curtailment cause.",
            resolution="Transmission explains part of the curtailment.",
            atoms=[AtomEmission(
                type="claim",
                text="Transmission limits explain part of California solar curtailment.")])],
        declaration_kind="frontier", declaration_summary="Crux-conditional frontier.",
        positions=[BasinPosition(hypothesis_text=HYP, condition="under cost weighting")],
        dissolve=Dissolve())
    result = stitch_harvest(stitch, vantage=make_vantage(farm="stitcher"),
                            corpus=corpus, question_id=Q, ts=TS)
    scored = [e["payload"] for e in result.events
              if e["kind"] == "edge" and e["payload"]["rel"] == "scored_against"]
    assert len(scored) == 1  # exactly one resolved cell
    assert scored[0]["src"] == ev.id and scored[0]["dst"] == hyp_id
    assert scored[0]["consistency"] == "inconsistent"
    assert result.unresolved  # the unrecorded evidence text is reported
    assert len(result.atom_ids) == 1  # investigation atom landed


def test_verify_harvest_upgrades_verified_via_reobservation():
    corpus, hyp_id, claim_id = _hyp_corpus()
    results = [VerificationResult(atom_id=claim_id, verified=True,
                                  evidence="CAISO curtailment reports corroborate the lag.",
                                  source="caiso.com"),
               VerificationResult(atom_id="c-000000000000", verified=True, evidence="x"),
               VerificationResult(atom_id=hyp_id, verified=False, evidence="inconclusive")]
    verifier = make_vantage(farm="verifier", persona="verifier")
    result = verify_harvest(results, corpus=corpus, vantage=verifier, ts=TS)
    assert result.atom_ids == [claim_id]
    assert result.unresolved == [{"atom_id": "c-000000000000"}]
    # replaying the original node + the verification event upgrades verified
    original = node_event(Node.create(type="claim", text=CLAIM, vantage=V,
                                      question_id=Q, ts=TS))
    reduced = reduce_events([original, *result.events])
    assert reduced.nodes[claim_id].verified is True
    assert reduced.nodes[claim_id].sightings == 2
```

Also add `from antfarm.schema import Node` to the imports at the top of the file if not already present.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_harvest.py -v`
Expected: FAIL with `ImportError: cannot import name 'critique_harvest'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/antfarm/harvest.py`:

```python
def critique_harvest(report: "CritiqueReport", *, vantage: Vantage, corpus: Corpus,
                     hypothesis_id: str, question_id: str, ts: str,
                     start_turn: int) -> HarvestResult:
    rel_for = {"rebutting": "rebuts", "undercutting": "undercuts"}
    atoms = [AtomEmission(type="claim", text=f.text) for f in report.findings]
    edges = [EdgeEmission(src=f.text, dst=f.target_text, rel=rel_for[f.classification])
             for f in report.findings]
    atoms.append(AtomEmission(type="claim", text=report.premortem))
    edges.append(EdgeEmission(src=report.premortem, dst=hypothesis_id, rel="undercuts"))
    result = _convert(atoms, edges, vantage=vantage, corpus=corpus,
                      question_id=question_id, ts=ts)
    rendered = "\n".join(
        f"[{f.severity}/{f.kind}] {f.text} (target: {f.target_text})"
        for f in report.findings)
    content = f"{report.summary}\n{rendered}\nPremortem: {report.premortem}"
    result.turns.append(Turn(turn=start_turn, role="user", phase="critique",
                             iteration=vantage.round, content=content))
    return result


def framing_harvest(output: "FramingOutput", *, vantage: Vantage, question_id: str,
                    ts: str) -> tuple[HarvestResult, list[dict]]:
    atoms = [AtomEmission(type="hypothesis", text=r.text) for r in output.rivals]
    result = _convert(atoms, [], vantage=vantage, corpus=Corpus(),
                      question_id=question_id, ts=ts)
    accepted_ids = set(result.atom_ids)
    rivals = [{"id": atom_id("hypothesis", r.text), "text": r.text, "is_null": r.is_null}
              for r in output.rivals
              if atom_id("hypothesis", r.text) in accepted_ids]
    return result, rivals


def stitch_harvest(output: "StitchOutput", *, vantage: Vantage, corpus: Corpus,
                   question_id: str, ts: str) -> HarvestResult:
    atoms = [a for inv in output.investigations for a in inv.atoms]
    edges = [e for inv in output.investigations for e in inv.edges]
    result = _convert(atoms, edges, vantage=vantage, corpus=corpus,
                      question_id=question_id, ts=ts)
    batch = {normalize_text(a.text): a for a in atoms}
    for cell in output.ach:
        src = resolve_ref(cell.evidence_text, batch, corpus)
        dst = resolve_ref(cell.hypothesis_text, batch, corpus)
        if src is None or dst is None:
            result.unresolved.append({"src": cell.evidence_text,
                                      "dst": cell.hypothesis_text,
                                      "rel": "scored_against"})
            continue
        result.events.append(edge_event(Edge(src=src, dst=dst, rel="scored_against",
                                             consistency=cell.consistency,
                                             vantage=vantage, ts=ts)))
    return result


def verify_harvest(results: "list[VerificationResult]", *, corpus: Corpus,
                   vantage: Vantage, ts: str) -> HarvestResult:
    out = HarvestResult()
    for item in results:
        node = corpus.nodes.get(item.atom_id)
        if node is None:
            out.unresolved.append({"atom_id": item.atom_id})
            continue
        if not item.verified:
            continue
        reobservation = Node.create(type=node.type, text=node.text, vantage=vantage,
                                    question_id=node.question_id, ts=ts, verified=True)
        out.events.append(node_event(reobservation))
        out.atom_ids.append(node.id)
    return out
```

Update the imports at the top of `src/antfarm/harvest.py` to include the new emission models:

```python
from antfarm.emission import (
    AtomBatch,
    AtomEmission,
    CritiqueReport,
    EdgeEmission,
    FramingOutput,
    ScoutRoundOutput,
    StitchOutput,
    VerificationResult,
)
```

and remove the quotes from the type hints once the imports are real (they are shown quoted above only so the append reads standalone; with the import block updated, write them unquoted: `report: CritiqueReport`, etc.).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_harvest.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
uv run ruff check src tests && uv run mypy src
git add src/antfarm/harvest.py tests/test_harvest.py
git commit -m "feat: critique, framing, stitch, and verification-floor harvests"
```

---

### Task 4: CONCLUDE gates and decision resolution

Script-enforced farm decisions (spec §5 Phase 2, §7 Lakatos/Popper rows). The scout *proposes* a decision; `resolve_decision` is the authority.

**Files:**
- Create: `src/antfarm/gates.py`
- Test: `tests/test_gates.py`

**Interfaces:**
- Consumes: `FarmDecision`, `TriggerEmission` (Task 1); `LedgerEntry` from `antfarm.transcript`; `find_unsublated_undercutters`, `Corpus` from plan 1; `helpers.make_corpus_node`, `helpers.make_edge`, `helpers.make_vantage`
- Produces: `GateResult(decision: FarmDecision, forced: bool = False, reasons: list[str] = [])` (pydantic); `degeneration_forced(ledger: list[LedgerEntry]) -> bool`; `farm_node_ids(corpus: Corpus, farm: str) -> set[str]`; `conclude_blockers(corpus, farm, triggers: list[TriggerEmission], ledger) -> list[str]`; `resolve_decision(*, scout_decision: FarmDecision, corpus: Corpus, farm: str, triggers, ledger, final_round: bool) -> GateResult`

- [ ] **Step 1: Write the failing test**

`tests/test_gates.py`:

```python
from helpers import make_corpus_node, make_edge

from antfarm.emission import TriggerEmission
from antfarm.gates import degeneration_forced, farm_node_ids, resolve_decision
from antfarm.reduce import Corpus
from antfarm.transcript import LedgerEntry

HIGH = TriggerEmission(text="A 2027 storage glut with flat solar growth falsifies this.",
                       severity="high")
LOW = TriggerEmission(text="A mild price dip would be surprising.", severity="low")


def _entry(novel: bool) -> LedgerEntry:
    return LedgerEntry(trigger="critique", change="patched", novel_content=novel)


def _farm_corpus(with_undercutter: bool) -> Corpus:
    # helpers' default vantage is farm "A", so every node here is farm A's
    thesis = make_corpus_node("Storage constraints bind solar growth through 2030.",
                              type="hypothesis")
    corpus = Corpus(nodes={thesis.id: thesis})
    if with_undercutter:
        attack = make_corpus_node("Storage statistics conflate contracted capacity.")
        corpus.nodes[attack.id] = attack
        corpus.edges.append(make_edge(attack.id, thesis.id, "undercuts"))
    return corpus


def test_degeneration_two_consecutive_content_free_patches():
    assert not degeneration_forced([_entry(False)])
    assert not degeneration_forced([_entry(False), _entry(True), _entry(False)])
    assert degeneration_forced([_entry(True), _entry(False), _entry(False)])


def test_farm_node_ids_uses_any_sighting_vantage():
    corpus = _farm_corpus(with_undercutter=False)
    assert farm_node_ids(corpus, "A") == set(corpus.nodes)
    assert farm_node_ids(corpus, "B") == set()


def test_conclude_blocked_without_high_trigger():
    result = resolve_decision(scout_decision="CONCLUDE",
                              corpus=_farm_corpus(False), farm="A",
                              triggers=[LOW], ledger=[], final_round=False)
    assert result.decision == "CONTINUE" and result.forced
    assert any("HIGH-severity" in r for r in result.reasons)


def test_conclude_blocked_by_unsublated_undercutter():
    result = resolve_decision(scout_decision="CONCLUDE",
                              corpus=_farm_corpus(True), farm="A",
                              triggers=[HIGH], ledger=[], final_round=False)
    assert result.decision == "CONTINUE"
    assert any("undercutter" in r for r in result.reasons)


def test_conclude_passes_when_gates_clear():
    corpus = _farm_corpus(True)
    # answer the undercutter with a live rebuttal - the challenge is no longer standing
    answer = make_corpus_node("Contracted-capacity inflation is corrected in the dataset.")
    corpus.nodes[answer.id] = answer
    attack_id = next(nid for nid, n in corpus.nodes.items()
                     if n.text.startswith("Storage statistics"))
    corpus.edges.append(make_edge(answer.id, attack_id, "rebuts"))
    result = resolve_decision(scout_decision="CONCLUDE", corpus=corpus, farm="A",
                              triggers=[HIGH, LOW], ledger=[_entry(True)],
                              final_round=False)
    assert result.decision == "CONCLUDE" and not result.forced


def test_concede_and_elevate_pass_through():
    for decision in ("CONCEDE", "ELEVATE"):
        result = resolve_decision(scout_decision=decision, corpus=Corpus(), farm="A",
                                  triggers=[], ledger=[], final_round=False)
        assert result.decision == decision and not result.forced


def test_degeneration_forces_elevate_on_continue():
    result = resolve_decision(scout_decision="CONTINUE", corpus=Corpus(), farm="A",
                              triggers=[], ledger=[_entry(False), _entry(False)],
                              final_round=False)
    assert result.decision == "ELEVATE" and result.forced


def test_final_round_never_returns_continue():
    blocked = resolve_decision(scout_decision="CONCLUDE", corpus=_farm_corpus(False),
                               farm="A", triggers=[], ledger=[], final_round=True)
    assert blocked.decision == "ELEVATE"
    assert any("round budget" in r for r in blocked.reasons)
    idle = resolve_decision(scout_decision="CONTINUE", corpus=Corpus(), farm="A",
                            triggers=[], ledger=[], final_round=True)
    assert idle.decision == "ELEVATE" and idle.forced
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_gates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'antfarm.gates'`

- [ ] **Step 3: Write minimal implementation**

`src/antfarm/gates.py`:

```python
"""Script-enforced farm decisions (spec §5 Phase 2). The scout proposes;
resolve_decision disposes. CONCLUDE needs >=1 HIGH falsification trigger,
no un-sublated undercutters against the farm's atoms, and a clean
degeneration ledger. Two consecutive novel-content-free patches force
ELEVATE (Lakatos, spec §7)."""

from pydantic import BaseModel, Field

from antfarm.emission import FarmDecision, TriggerEmission
from antfarm.graph import find_unsublated_undercutters
from antfarm.reduce import Corpus
from antfarm.transcript import LedgerEntry


class GateResult(BaseModel):
    decision: FarmDecision
    forced: bool = False
    reasons: list[str] = Field(default_factory=list)


def degeneration_forced(ledger: list[LedgerEntry]) -> bool:
    return (len(ledger) >= 2
            and not ledger[-1].novel_content
            and not ledger[-2].novel_content)


def farm_node_ids(corpus: Corpus, farm: str) -> set[str]:
    return {nid for nid, node in corpus.nodes.items()
            if any(v.farm == farm for v in node.vantages)}


def conclude_blockers(corpus: Corpus, farm: str, triggers: list[TriggerEmission],
                      ledger: list[LedgerEntry]) -> list[str]:
    reasons = []
    if not any(t.severity == "high" for t in triggers):
        reasons.append("no HIGH-severity falsification trigger on record")
    mine = farm_node_ids(corpus, farm)
    standing = [(src, dst) for src, dst in find_unsublated_undercutters(corpus)
                if dst in mine]
    if standing:
        reasons.append(
            f"{len(standing)} un-sublated undercutter(s) against this farm's atoms")
    if degeneration_forced(ledger):
        reasons.append("degeneration ledger unclean: "
                       "two consecutive novel-content-free patches")
    return reasons


_EXHAUSTED = "round budget exhausted"
_DEGENERATE = "degeneration ledger: two consecutive novel-content-free patches"


def resolve_decision(*, scout_decision: FarmDecision, corpus: Corpus, farm: str,
                     triggers: list[TriggerEmission], ledger: list[LedgerEntry],
                     final_round: bool) -> GateResult:
    if scout_decision in ("CONCEDE", "ELEVATE"):
        return GateResult(decision=scout_decision)
    if scout_decision == "CONCLUDE":
        reasons = conclude_blockers(corpus, farm, triggers, ledger)
        if not reasons:
            return GateResult(decision="CONCLUDE")
        if final_round:
            return GateResult(decision="ELEVATE", forced=True,
                              reasons=[*reasons, _EXHAUSTED])
        return GateResult(decision="CONTINUE", forced=True, reasons=reasons)
    if degeneration_forced(ledger):
        return GateResult(decision="ELEVATE", forced=True, reasons=[_DEGENERATE])
    if final_round:
        return GateResult(decision="ELEVATE", forced=True, reasons=[_EXHAUSTED])
    return GateResult(decision="CONTINUE")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_gates.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
uv run ruff check src tests && uv run mypy src
git add src/antfarm/gates.py tests/test_gates.py
git commit -m "feat: script-enforced CONCLUDE gates and forced-decision resolution"
```

---

### Task 5: Tripwires and ACH/E analysis

Phase 0's firing mechanics, Phase 7's registration, Phase 5's winner-by-least-inconsistency, and the derived E band (spec §5, §7, §8).

Tripwire graph shape: a tripwire node watches a hypothesis via an edge `hypothesis --depends_on--> tripwire`. Firing walks `blast_radius` (ancestors along `depends_on`) from each watched node, so anything transitively depending on a watched hypothesis is contested too.

**Files:**
- Create: `src/antfarm/tripwires.py`
- Create: `src/antfarm/analysis.py`
- Test: `tests/test_tripwires.py`
- Test: `tests/test_analysis.py`

**Interfaces:**
- Consumes: `TriggerEmission`, `Band` (Task 1); `node_event`, `edge_event`, `status_event`; `build_graph`, `blast_radius`; `Corpus`; `Node`, `Edge`, `Vantage`; `helpers` builders
- Produces: `register_tripwires(triggers: list[TriggerEmission], hypothesis_id: str, *, vantage, question_id, ts) -> list[dict]` (HIGH severity only); `standing_tripwires(corpus) -> list[dict]` (`{"id","text","watches"}` for live tripwire nodes); `fire_tripwire(corpus, tripwire_id, evidence_text, *, vantage, question_id, ts) -> tuple[list[dict], list[str]]` (events + sorted affected ids); `ach_scores(corpus, question_id) -> dict` (`{"inconsistency": {hyp_id: int}, "discarded_nondiagnostic": [evidence_id]}`); `ach_winner(corpus, question_id) -> dict` (`{"winner": id | None, "tied": [...], ...scores}`); `derive_e(corpus, question_id) -> Band`

- [ ] **Step 1: Write the failing tests**

`tests/test_tripwires.py`:

```python
from helpers import make_corpus_node, make_edge, make_vantage

from antfarm.emission import TriggerEmission
from antfarm.events import node_event
from antfarm.reduce import Corpus, reduce_events
from antfarm.schema import Node
from antfarm.tripwires import fire_tripwire, register_tripwires, standing_tripwires

V = make_vantage(farm="A")
TS = "2026-07-04T00:00:00Z"
TRIGGER = TriggerEmission(
    text="A 2027 storage glut with flat solar growth falsifies the storage thesis.",
    severity="high")


def _corpus_with_hypothesis():
    hyp = make_corpus_node("Storage constraints bind solar growth through 2030.",
                           type="hypothesis")
    dependent = make_corpus_node("Solar installers should hedge storage exposure.")
    corpus = Corpus(nodes={hyp.id: hyp, dependent.id: dependent},
                    edges=[make_edge(dependent.id, hyp.id, "depends_on")])
    return corpus, hyp.id, dependent.id


def test_register_emits_tripwire_watching_hypothesis_high_only():
    corpus, hyp_id, _ = _corpus_with_hypothesis()
    low = TriggerEmission(text="A mild dip would be surprising.", severity="low")
    events = register_tripwires([TRIGGER, low], hyp_id, vantage=V,
                                question_id="q-1", ts=TS)
    assert [e["kind"] for e in events] == ["node", "edge"]
    assert events[0]["payload"]["type"] == "tripwire"
    edge = events[1]["payload"]
    assert edge["src"] == hyp_id and edge["rel"] == "depends_on"


def test_standing_tripwires_lists_live_with_watches():
    corpus, hyp_id, _ = _corpus_with_hypothesis()
    events = [node_event(Node.model_validate(n.model_dump()))
              for n in corpus.nodes.values()]
    events += [{"kind": "edge", "payload": e.model_dump()} for e in corpus.edges]
    events += register_tripwires([TRIGGER], hyp_id, vantage=V, question_id="q-1", ts=TS)
    reduced = reduce_events(events)
    standing = standing_tripwires(reduced)
    assert len(standing) == 1
    assert standing[0]["watches"] == [hyp_id]


def test_fire_contests_watched_and_blast_radius():
    corpus, hyp_id, dep_id = _corpus_with_hypothesis()
    reg = register_tripwires([TRIGGER], hyp_id, vantage=V, question_id="q-1", ts=TS)
    events = [node_event(Node.model_validate(n.model_dump()))
              for n in corpus.nodes.values()]
    events += [{"kind": "edge", "payload": e.model_dump()} for e in corpus.edges]
    events += reg
    reduced = reduce_events(events)
    trip_id = reg[0]["payload"]["id"]

    fire_events, affected = fire_tripwire(
        reduced, trip_id, "A storage glut arrived in 2027 while solar growth was flat.",
        vantage=make_vantage(farm="sentinel"), question_id="q-1", ts=TS)
    assert affected == sorted([hyp_id, dep_id])
    final = reduce_events(events + fire_events)
    assert final.nodes[hyp_id].status == "contested"
    assert final.nodes[dep_id].status == "contested"
    undercuts = [e for e in final.edges if e.rel == "undercuts"]
    assert len(undercuts) == 1 and undercuts[0].dst == hyp_id
```

`tests/test_analysis.py`:

```python
from helpers import make_corpus_node, make_edge

from antfarm.analysis import ach_winner, derive_e
from antfarm.reduce import Corpus


def _ach_corpus():
    h1 = make_corpus_node("Storage constraints bind solar growth.", type="hypothesis")
    h2 = make_corpus_node("No single constraint binds solar growth.", type="hypothesis")
    e1 = make_corpus_node("California curtailed 2.4 TWh of solar in 2024.",
                          type="evidence")
    e2 = make_corpus_node("Battery installs rose 40% in 2024.", type="evidence")
    corpus = Corpus(nodes={n.id: n for n in (h1, h2, e1, e2)}, edges=[
        # e1 cuts against h2 only; e2 is consistent with everything (non-diagnostic)
        make_edge(e1.id, h1.id, "scored_against", consistency="consistent"),
        make_edge(e1.id, h2.id, "scored_against", consistency="inconsistent"),
        make_edge(e2.id, h1.id, "scored_against", consistency="consistent"),
        make_edge(e2.id, h2.id, "scored_against", consistency="consistent"),
    ])
    return corpus, h1.id, h2.id, e2.id


def test_winner_by_least_inconsistency_discarding_nondiagnostic():
    corpus, h1_id, h2_id, e2_id = _ach_corpus()
    result = ach_winner(corpus, "q-1")
    assert result["winner"] == h1_id
    assert result["inconsistency"][h2_id] == 1
    assert result["discarded_nondiagnostic"] == [e2_id]


def test_tie_yields_no_winner():
    corpus, h1_id, h2_id, _ = _ach_corpus()
    corpus.edges = []  # no diagnostic evidence at all
    result = ach_winner(corpus, "q-1")
    assert result["winner"] is None
    assert sorted(result["tied"]) == sorted([h1_id, h2_id])


def test_derive_e_counts_live_verified_high_diagnostic_evidence():
    corpus = Corpus()
    assert derive_e(corpus, "q-1") == "low"
    texts = [f"Distinct verified diagnostic fact number {i} about storage." for i in range(5)]
    for i, text in enumerate(texts):
        node = make_corpus_node(text, type="evidence", verified=True,
                                diagnosticity="high")
        corpus.nodes[node.id] = node
        if i == 1:
            assert derive_e(corpus, "q-1") == "med"  # 2 -> med
    assert derive_e(corpus, "q-1") == "high"  # 5 -> high
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tripwires.py tests/test_analysis.py -v`
Expected: FAIL with `ModuleNotFoundError` for both modules

- [ ] **Step 3: Write minimal implementations**

`src/antfarm/tripwires.py`:

```python
"""Standing tripwires (spec §5 Phase 0, §8): falsification triggers become
stored sensors; a fired tripwire contests its watched hypotheses and
everything in their depends_on blast radius. The map self-reports staleness."""

from antfarm.emission import TriggerEmission
from antfarm.events import edge_event, node_event, status_event
from antfarm.graph import blast_radius, build_graph
from antfarm.reduce import Corpus
from antfarm.schema import Edge, Node, Vantage


def register_tripwires(triggers: list[TriggerEmission], hypothesis_id: str, *,
                       vantage: Vantage, question_id: str, ts: str) -> list[dict]:
    events: list[dict] = []
    for trigger in triggers:
        if trigger.severity != "high":
            continue
        node = Node.create(type="tripwire", text=trigger.text, vantage=vantage,
                           question_id=question_id, ts=ts)
        events.append(node_event(node))
        events.append(edge_event(Edge(src=hypothesis_id, dst=node.id, rel="depends_on",
                                      vantage=vantage, ts=ts)))
    return events


def standing_tripwires(corpus: Corpus) -> list[dict]:
    out = []
    for nid, node in corpus.nodes.items():
        if node.type != "tripwire" or node.status != "live":
            continue
        watches = [e.src for e in corpus.edges
                   if e.rel == "depends_on" and e.dst == nid]
        out.append({"id": nid, "text": node.text, "watches": watches})
    return sorted(out, key=lambda t: str(t["id"]))


def fire_tripwire(corpus: Corpus, tripwire_id: str, evidence_text: str, *,
                  vantage: Vantage, question_id: str,
                  ts: str) -> tuple[list[dict], list[str]]:
    watched = [e.src for e in corpus.edges
               if e.rel == "depends_on" and e.dst == tripwire_id
               and e.src in corpus.nodes]
    graph = build_graph(corpus)
    affected: set[str] = set(watched)
    for wid in watched:
        affected |= blast_radius(graph, wid)
    events: list[dict] = []
    evidence = Node.create(type="evidence", text=evidence_text, vantage=vantage,
                           question_id=question_id, ts=ts)
    events.append(node_event(evidence))
    for wid in watched:
        events.append(edge_event(Edge(src=evidence.id, dst=wid, rel="undercuts",
                                      vantage=vantage, ts=ts)))
    for nid in sorted(affected):
        if corpus.nodes[nid].status == "live":
            events.append(status_event(nid, "contested", ts=ts))
    return events, sorted(affected)
```

`src/antfarm/analysis.py`:

```python
"""Phase 5/7 computed judgments: ACH winner by least inconsistency with
non-diagnostic evidence discarded (Heuer, spec §5 Phase 5), and the derived
E band (spec §7 - diagnosticity counts now, rarefaction slope in plan 3)."""

from collections import defaultdict

from antfarm.emission import Band
from antfarm.reduce import Corpus


def ach_scores(corpus: Corpus, question_id: str) -> dict:
    cells: dict[str, dict[str, str]] = defaultdict(dict)
    for edge in corpus.edges:
        if edge.rel != "scored_against" or edge.consistency is None:
            continue
        cells[edge.src][edge.dst] = edge.consistency
    discarded = sorted(ev for ev, row in cells.items()
                       if len(row) >= 2 and "inconsistent" not in row.values())
    hypotheses = {nid for nid, n in corpus.nodes.items()
                  if n.type == "hypothesis" and n.question_id == question_id}
    inconsistency = dict.fromkeys(sorted(hypotheses), 0)
    for ev, row in cells.items():
        if ev in discarded:
            continue
        for hyp, consistency in row.items():
            if consistency == "inconsistent" and hyp in inconsistency:
                inconsistency[hyp] += 1
    return {"inconsistency": inconsistency, "discarded_nondiagnostic": discarded}


def ach_winner(corpus: Corpus, question_id: str) -> dict:
    scores = ach_scores(corpus, question_id)
    live = [nid for nid, n in corpus.nodes.items()
            if n.type == "hypothesis" and n.question_id == question_id
            and n.status in ("live", "contested")]
    counts = {nid: scores["inconsistency"].get(nid, 0) for nid in live}
    if not counts:
        return {"winner": None, "tied": [], **scores}
    best = min(counts.values())
    winners = sorted(nid for nid, c in counts.items() if c == best)
    if len(winners) == 1:
        return {"winner": winners[0], "tied": [], **scores}
    return {"winner": None, "tied": winners, **scores}


def derive_e(corpus: Corpus, question_id: str) -> Band:
    count = sum(
        1 for node in corpus.nodes.values()
        if node.type == "evidence" and node.question_id == question_id
        and node.status == "live" and node.verified and node.diagnosticity == "high")
    if count < 2:
        return "low"
    if count < 5:
        return "med"
    return "high"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tripwires.py tests/test_analysis.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
uv run ruff check src tests && uv run mypy src
git add src/antfarm/tripwires.py src/antfarm/analysis.py tests/test_tripwires.py tests/test_analysis.py
git commit -m "feat: tripwire register/fire with blast radius; ACH winner and derived E band"
```

---

### Task 6: persona-swap counterfactual (splice + regeneration package)

The third counterfactual (spec §9.2). shuffle and graft landed in plan 1 as pure transforms; persona-swap needs a model to regenerate rounds k..n, so the pure parts here are: packaging the host context for the regeneration agent, converting its schema-forced output to `Turn`s, and splicing.

**Files:**
- Modify: `src/antfarm/counterfactual.py` (append)
- Test: `tests/test_counterfactual.py` (append)

**Interfaces:**
- Consumes: `Turn`, `_renumber` (existing); `PersonaSwapOutput`, `RegeneratedTurn` (Task 1)
- Produces: `swap_package(turns: list[Turn], start_iteration: int) -> dict` (`{"eligible": bool, "context": [turn dicts], "regen_iterations": [int], "start_iteration": int}`); `regenerated_to_turns(output: PersonaSwapOutput) -> list[Turn]`; `persona_swap(host: list[Turn], regenerated: list[Turn], start_iteration: int) -> list[Turn]`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_counterfactual.py`:

```python
from antfarm.counterfactual import persona_swap, regenerated_to_turns, swap_package
from antfarm.emission import PersonaSwapOutput, RegeneratedTurn


def test_swap_package_splits_at_iteration_boundary():
    turns = _turns("host")
    pkg = swap_package(turns, start_iteration=2)
    assert pkg["eligible"] is True
    assert [t["iteration"] for t in pkg["context"]] == [1, 1]
    assert pkg["regen_iterations"] == [2, 3]


def test_swap_package_ineligible_without_both_sides():
    turns = _turns("host", n_iterations=1)
    assert swap_package(turns, start_iteration=2)["eligible"] is False
    assert swap_package(turns, start_iteration=1)["eligible"] is False


def test_persona_swap_splices_regenerated_turns():
    host = _turns("host")
    regen = regenerated_to_turns(PersonaSwapOutput(turns=[
        RegeneratedTurn(phase="expand", iteration=2, content="alt persona expand"),
        RegeneratedTurn(phase="compress", iteration=2, content="alt persona compress"),
    ]))
    swapped = persona_swap(host, regen, start_iteration=2)
    assert [t.content for t in swapped] == [
        "host iteration 1 step 0", "host iteration 1 step 1",
        "alt persona expand", "alt persona compress",
    ]
    assert [t.turn for t in swapped] == list(range(4))
    assert all(t.role == "assistant" for t in regen)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_counterfactual.py -v`
Expected: FAIL with `ImportError: cannot import name 'persona_swap'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/antfarm/counterfactual.py`:

```python
from antfarm.emission import PersonaSwapOutput


def swap_package(turns: list[Turn], start_iteration: int) -> dict:
    kept = [t.model_dump() for t in turns if t.iteration < start_iteration]
    regen = sorted({t.iteration for t in turns if t.iteration >= start_iteration})
    return {"eligible": bool(kept) and bool(regen), "context": kept,
            "regen_iterations": regen, "start_iteration": start_iteration}


def regenerated_to_turns(output: PersonaSwapOutput) -> list[Turn]:
    return [Turn(turn=i, role="assistant", phase=t.phase, iteration=t.iteration,
                 content=t.content)
            for i, t in enumerate(output.turns)]


def persona_swap(host: list[Turn], regenerated: list[Turn],
                 start_iteration: int) -> list[Turn]:
    kept = [t for t in host if t.iteration < start_iteration]
    return _renumber(kept + regenerated)
```

(Import note: `antfarm.emission` imports `antfarm.transcript`, and `antfarm.counterfactual` already imports `antfarm.transcript` — no cycle.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_counterfactual.py -v`
Expected: 5 passed (2 existing + 3 new)

- [ ] **Step 5: Commit**

```bash
uv run ruff check src tests && uv run mypy src
git add src/antfarm/counterfactual.py tests/test_counterfactual.py
git commit -m "feat: persona-swap counterfactual - package, regenerate, splice"
```

---

### Task 7: Farm state directory and briefs

Per-farm continuity lives in `farms/<run>/<farm>/` — turns, ledger, triggers, critiques, meta, outcome. Scouts get continuity by reading this dir; blind-critics read `turns.jsonl` as an authorless artifact. `brief.py` computes the warm-start brief (Phase 1), the stitch brief (Phase 5), the verification queue (Phase 4), and the hole probe (Phase 6).

**Files:**
- Create: `src/antfarm/farm.py`
- Create: `src/antfarm/brief.py`
- Test: `tests/test_farm.py`
- Test: `tests/test_brief.py`

**Interfaces:**
- Consumes: `Turn`, `LedgerEntry` from `antfarm.transcript`; `CritiqueReport`, `TriggerEmission` (Task 1); `build_graph`, `compute_centrality`, `compute_view`, `extract_cruxes` (plan 1); `standing_tripwires` (Task 5); `EmbedFn`, `cosine` (plan 1); `helpers` builders
- Produces (`antfarm.farm`): `FarmMeta(farm, hypothesis_id, hypothesis_text, persona, family, question_id, question_text)`; `farm_dir(corpus_dir: Path, run: str, farm: str) -> Path`; `init_farm(corpus_dir, run, farm, meta: FarmMeta) -> Path` (creates dirs, writes meta.json, appends the turn-0 user brief); `read_meta(d) -> FarmMeta`; `append_turns(d, turns)` / `read_turns(d) -> list[Turn]` / `next_turn_index(d) -> int`; `append_ledger(d, entry)` / `read_ledger(d) -> list[LedgerEntry]`; `append_triggers(d, triggers)` / `read_triggers(d) -> list[TriggerEmission]`; `write_critique(d, round: int, report) -> Path`; `write_outcome(d, decision: str, died_because: str | None)` / `read_outcome(d) -> dict | None`; `last_compressed(d) -> str | None`
- Produces (`antfarm.brief`): `warm_brief(corpus, question_id: str, runs_root: Path) -> dict`; `stitch_brief(corpus, corpus_dir: Path, run: str) -> dict`; `verification_queue(corpus) -> list[dict]` (`{"id","text","type","round","late"}` — every live unverified single-sighting model-sensor claim/evidence, sorted latest-round first; `late` is round ≥ 2, the mandatory floor); `probe(corpus, embed: EmbedFn, text: str, threshold: float = 0.67) -> dict` (`{"novel": bool, "nearest": [{"id","score","text"}]}`)

- [ ] **Step 1: Write the failing tests**

`tests/test_farm.py`:

```python
from helpers import make_vantage  # noqa: F401 - ensures helpers imports stay shared

from antfarm.emission import CritiqueFinding, CritiqueReport, TriggerEmission
from antfarm.farm import (
    FarmMeta,
    append_ledger,
    append_triggers,
    append_turns,
    init_farm,
    last_compressed,
    next_turn_index,
    read_ledger,
    read_meta,
    read_outcome,
    read_triggers,
    read_turns,
    write_critique,
    write_outcome,
)
from antfarm.transcript import LedgerEntry, Turn

META = FarmMeta(farm="A", hypothesis_id="h-000000000001",
                hypothesis_text="Storage binds solar growth.",
                persona="a municipal procurement officer", family="opus",
                question_id="q-1", question_text="What limits solar growth?")


def test_init_farm_writes_meta_and_brief_turn(tmp_path):
    d = init_farm(tmp_path, "r0001", "A", META)
    assert read_meta(d) == META
    turns = read_turns(d)
    assert len(turns) == 1 and turns[0].role == "user" and turns[0].turn == 0
    assert META.hypothesis_text in turns[0].content
    assert META.persona in turns[0].content
    assert next_turn_index(d) == 1


def test_turn_ledger_trigger_roundtrips(tmp_path):
    d = init_farm(tmp_path, "r0001", "A", META)
    append_turns(d, [Turn(turn=1, role="assistant", phase="expand", iteration=1,
                          content="expanding"),
                     Turn(turn=2, role="assistant", phase="compress", iteration=1,
                          content="the compressed state")])
    assert next_turn_index(d) == 3
    assert last_compressed(d) == "the compressed state"

    entry = LedgerEntry(trigger="critique", change="qualified", novel_content=True)
    append_ledger(d, entry)
    assert read_ledger(d) == [entry]

    trigger = TriggerEmission(text="A storage glut falsifies this.", severity="high")
    append_triggers(d, [trigger])
    append_triggers(d, [trigger])
    assert read_triggers(d) == [trigger, trigger]


def test_critique_and_outcome_files(tmp_path):
    d = init_farm(tmp_path, "r0001", "A", META)
    report = CritiqueReport(findings=[CritiqueFinding(
        target_text="x", kind="warrant_probe", classification="undercutting",
        severity="med", text="The warrant assumes static demand.")],
        premortem="The thesis failed because demand shifted.", summary="one probe")
    path = write_critique(d, 1, report)
    assert path.name == "r01.json" and path.parent.name == "critiques"

    assert read_outcome(d) is None
    write_outcome(d, "CONCLUDE", None)
    assert read_outcome(d) == {"decision": "CONCLUDE", "died_because": None}


def test_empty_farm_dir_reads_are_safe(tmp_path):
    d = tmp_path / "farms" / "r0001" / "Z"
    d.mkdir(parents=True)
    assert read_turns(d) == [] and read_ledger(d) == [] and read_triggers(d) == []
    assert next_turn_index(d) == 0 and last_compressed(d) is None
```

`tests/test_brief.py`:

```python
import json

from helpers import make_corpus_node, make_edge, make_vantage

from antfarm.brief import probe, stitch_brief, verification_queue, warm_brief
from antfarm.cluster import cosine  # noqa: F401
from antfarm.farm import FarmMeta, append_turns, init_farm, write_outcome
from antfarm.reduce import Corpus
from antfarm.transcript import Turn


def _seeded_corpus():
    view_claim = make_corpus_node("Storage capacity limits solar deployment growth.",
                                  verified=True)
    crux = make_corpus_node("Whether curtailment reflects storage or transmission.",
                            status="contested")
    dead = make_corpus_node("Fusion arrives before 2035 at grid scale.",
                            type="hypothesis", status="conceded",
                            died_because="no deployment evidence")
    return Corpus(nodes={n.id: n for n in (view_claim, crux, dead)}), view_claim, crux, dead


def test_warm_brief_carries_view_cruxes_conceded_and_declaration(tmp_path):
    corpus, view_claim, crux, dead = _seeded_corpus()
    run_dir = tmp_path / "r0001"
    run_dir.mkdir()
    (run_dir / "declaration.json").write_text(json.dumps({"kind": "basin"}))
    brief = warm_brief(corpus, "q-1", tmp_path)
    assert brief["view"][0]["id"] == view_claim.id
    assert brief["cruxes"][0]["id"] == crux.id
    assert brief["conceded"] == [{"text": dead.text,
                                  "died_because": "no deployment evidence"}]
    assert brief["declaration"] == {"kind": "basin"}


def test_stitch_brief_reads_farm_dirs_and_inventories(tmp_path):
    corpus, *_ = _seeded_corpus()
    ev = make_corpus_node("California curtailed 2.4 TWh of solar in 2024.",
                          type="evidence", strength=4, verified=True)
    corpus.nodes[ev.id] = ev
    meta = FarmMeta(farm="A", hypothesis_id="h-000000000001",
                    hypothesis_text="Storage binds growth.", persona="p",
                    family="opus", question_id="q-1", question_text="q")
    d = init_farm(tmp_path, "r0001", "A", meta)
    append_turns(d, [Turn(turn=1, role="assistant", phase="compress", iteration=1,
                          content="final state")])
    write_outcome(d, "CONCLUDE", None)
    brief = stitch_brief(corpus, tmp_path, "r0001")
    assert brief["farms"][0]["compressed_state"] == "final state"
    assert brief["farms"][0]["outcome"]["decision"] == "CONCLUDE"
    assert any(e["id"] == ev.id for e in brief["evidence"])
    assert any(h["status"] == "conceded" for h in brief["hypotheses"])


def test_verification_queue_flags_late_singletons_first():
    # make_corpus_node stamps helpers.V (round 1); rebuild `late` at round 3
    early = make_corpus_node("Early-round unverified claim about panel costs.")
    late = make_corpus_node("Late-round novel claim about interconnection queues.")
    late = late.model_copy(update={"vantage": make_vantage(round=3),
                                   "vantages": [make_vantage(round=3)]})
    verified = make_corpus_node("Already verified claim.", verified=True)
    corpus = Corpus(nodes={n.id: n for n in (early, late, verified)})
    queue = verification_queue(corpus)
    assert [q["id"] for q in queue] == [late.id, early.id]
    assert queue[0]["late"] is True and queue[1]["late"] is False


def test_probe_flags_duplicate_and_novel(tmp_path):
    corpus, view_claim, *_ = _seeded_corpus()

    def fake_embed(texts):
        return [[1.0, 0.0] if "storage" in t.lower() else [0.0, 1.0] for t in texts]

    dup = probe(corpus, fake_embed, "STORAGE capacity limits things.")
    assert dup["novel"] is False and dup["nearest"][0]["score"] == 1.0
    novel = probe(corpus, fake_embed, "Nobody has considered permitting reform.")
    assert novel["novel"] is True


def test_probe_on_empty_corpus_is_novel():
    assert probe(Corpus(), lambda ts: [[1.0]] * len(ts), "anything") == {
        "novel": True, "nearest": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_farm.py tests/test_brief.py -v`
Expected: FAIL with `ModuleNotFoundError` for both modules

- [ ] **Step 3: Write minimal implementations**

`src/antfarm/farm.py`:

```python
"""Per-farm state directory: the scout's continuity, the critic's input,
Phase 7's transcript source. Layout: farms/<run>/<farm>/{meta.json,
turns.jsonl, ledger.jsonl, triggers.jsonl, critiques/rNN.json, outcome.json}."""

import json
from pathlib import Path

from pydantic import BaseModel

from antfarm.emission import CritiqueReport, TriggerEmission
from antfarm.transcript import LedgerEntry, Turn


class FarmMeta(BaseModel):
    farm: str
    hypothesis_id: str
    hypothesis_text: str
    persona: str
    family: str
    question_id: str
    question_text: str


def farm_dir(corpus_dir: Path, run: str, farm: str) -> Path:
    return corpus_dir / "farms" / run / farm


def init_farm(corpus_dir: Path, run: str, farm: str, meta: FarmMeta) -> Path:
    d = farm_dir(corpus_dir, run, farm)
    (d / "critiques").mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    brief = (f"Question: {meta.question_text}\n"
             f"Assigned hypothesis: {meta.hypothesis_text}\n"
             f"Persona: {meta.persona}")
    append_turns(d, [Turn(turn=0, role="user", phase=None, iteration=1, content=brief)])
    return d


def read_meta(d: Path) -> FarmMeta:
    return FarmMeta.model_validate_json((d / "meta.json").read_text(encoding="utf-8"))


def _append_jsonl(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def append_turns(d: Path, turns: list[Turn]) -> None:
    _append_jsonl(d / "turns.jsonl", [t.model_dump_json() for t in turns])


def read_turns(d: Path) -> list[Turn]:
    return [Turn.model_validate(x) for x in _read_jsonl(d / "turns.jsonl")]


def next_turn_index(d: Path) -> int:
    return len(read_turns(d))


def append_ledger(d: Path, entry: LedgerEntry) -> None:
    _append_jsonl(d / "ledger.jsonl", [entry.model_dump_json()])


def read_ledger(d: Path) -> list[LedgerEntry]:
    return [LedgerEntry.model_validate(x) for x in _read_jsonl(d / "ledger.jsonl")]


def append_triggers(d: Path, triggers: list[TriggerEmission]) -> None:
    _append_jsonl(d / "triggers.jsonl", [t.model_dump_json() for t in triggers])


def read_triggers(d: Path) -> list[TriggerEmission]:
    return [TriggerEmission.model_validate(x) for x in _read_jsonl(d / "triggers.jsonl")]


def write_critique(d: Path, round: int, report: CritiqueReport) -> Path:
    path = d / "critiques" / f"r{round:02d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_outcome(d: Path, decision: str, died_because: str | None) -> None:
    (d / "outcome.json").write_text(
        json.dumps({"decision": decision, "died_because": died_because}),
        encoding="utf-8")


def read_outcome(d: Path) -> dict | None:
    path = d / "outcome.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def last_compressed(d: Path) -> str | None:
    compressed = [t.content for t in read_turns(d) if t.phase == "compress"]
    return compressed[-1] if compressed else None
```

`src/antfarm/brief.py`:

```python
"""Computed briefs: warm start (Phase 1), stitch input (Phase 5), the
verification queue (Phase 4 floor), and the hole probe (Phase 6)."""

import json
from pathlib import Path

from antfarm.cluster import EmbedFn, cosine
from antfarm.farm import last_compressed, read_meta, read_outcome
from antfarm.graph import build_graph, compute_centrality, compute_view, extract_cruxes
from antfarm.reduce import Corpus
from antfarm.tripwires import standing_tripwires

_PROBE_TYPES = ("claim", "evidence", "hypothesis", "tension")


def warm_brief(corpus: Corpus, question_id: str, runs_root: Path) -> dict:
    graph = build_graph(corpus)
    cent = compute_centrality(graph)
    view_ids = compute_view(corpus, cent)
    top = sorted(view_ids, key=lambda nid: cent.get(nid, 0.0), reverse=True)[:10]
    cruxes = extract_cruxes(corpus, cent)
    conceded = [{"text": n.text, "died_because": n.died_because}
                for n in corpus.nodes.values()
                if n.type == "hypothesis" and n.status == "conceded"]
    declaration = None
    declarations = sorted(runs_root.glob("*/declaration.json")) if runs_root.exists() else []
    if declarations:
        declaration = json.loads(declarations[-1].read_text(encoding="utf-8"))
    return {
        "question_id": question_id,
        "view": [{"id": nid, "text": corpus.nodes[nid].text} for nid in top],
        "cruxes": [{"id": nid, "text": corpus.nodes[nid].text} for nid in cruxes],
        "conceded": conceded,
        "tripwires": len(standing_tripwires(corpus)),
        "declaration": declaration,
    }


def stitch_brief(corpus: Corpus, corpus_dir: Path, run: str) -> dict:
    farms = []
    farms_root = corpus_dir / "farms" / run
    if farms_root.exists():
        for d in sorted(farms_root.iterdir()):
            if not (d / "meta.json").exists():
                continue
            meta = read_meta(d)
            farms.append({"farm": meta.farm, "hypothesis_id": meta.hypothesis_id,
                          "hypothesis_text": meta.hypothesis_text,
                          "compressed_state": last_compressed(d),
                          "outcome": read_outcome(d)})
    evidence = [{"id": nid, "text": n.text, "strength": n.strength,
                 "diagnosticity": n.diagnosticity, "verified": n.verified}
                for nid, n in sorted(corpus.nodes.items()) if n.type == "evidence"]
    hypotheses = [{"id": nid, "text": n.text, "status": n.status}
                  for nid, n in sorted(corpus.nodes.items()) if n.type == "hypothesis"]
    return {"farms": farms, "evidence": evidence, "hypotheses": hypotheses}


def verification_queue(corpus: Corpus) -> list[dict]:
    out = []
    for nid, node in corpus.nodes.items():
        if (node.type in ("claim", "evidence") and node.status == "live"
                and not node.verified and node.sightings == 1
                and node.vantages and node.vantages[0].sensor == "model"):
            first_round = node.vantages[0].round
            out.append({"id": nid, "text": node.text, "type": node.type,
                        "round": first_round, "late": first_round >= 2})
    return sorted(out, key=lambda item: (-item["round"], item["id"]))


def probe(corpus: Corpus, embed: EmbedFn, text: str, threshold: float = 0.67) -> dict:
    candidates = [(nid, node.text) for nid, node in sorted(corpus.nodes.items())
                  if node.type in _PROBE_TYPES]
    if not candidates:
        return {"novel": True, "nearest": []}
    vectors = embed([text] + [c[1] for c in candidates])
    query, rest = vectors[0], vectors[1:]
    scored = sorted(
        ({"id": nid, "score": cosine(query, vec), "text": ctext}
         for (nid, ctext), vec in zip(candidates, rest, strict=True)),
        key=lambda hit: -hit["score"])
    nearest = scored[:3]
    return {"novel": nearest[0]["score"] < threshold, "nearest": nearest}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_farm.py tests/test_brief.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
uv run ruff check src tests && uv run mypy src
git add src/antfarm/farm.py src/antfarm/brief.py tests/test_farm.py tests/test_brief.py
git commit -m "feat: farm state dirs and computed briefs (warm start, stitch, verify queue, probe)"
```

---

### Task 8: The `python -m antfarm` CLI — the workflow's only door into the corpus

Every deterministic pipeline step is a subcommand emitting one JSON object on stdout. The workflow's clerk agent runs these; nothing else writes to the corpus. Also adds the offline `hash_embed` and a file-backed embedding cache so repeated CLI invocations don't re-embed the corpus.

**Files:**
- Modify: `src/antfarm/cluster.py` (append `hash_embed`, `CachedEmbed`)
- Create: `src/antfarm/cli.py`
- Create: `src/antfarm/__main__.py`
- Test: `tests/test_cli.py`
- Modify: `tests/helpers.py` (append shared pipeline fixtures)

**Interfaces:**
- Consumes: everything from Tasks 1–7 plus plan 1 (`read_events`, `append_events`, `reduce_events`, `EmbeddingMatcher`, `CorpusStore`)
- Produces: `hash_embed(texts) -> list[list[float]]` (deterministic 256-dim hashed word unigrams+bigrams, no downloads — discriminative enough that distinct sentences stay below the 0.67 threshold while identical text scores 1.0); `CachedEmbed(path: Path, base: EmbedFn)` callable; `antfarm.cli.main(argv: list[str] | None = None) -> dict` (parses, dispatches, prints JSON, returns the dict); env switch `ANTFARM_EMBED=hash`; subcommands: `schemas`, `run-new`, `brief`, `farm-init`, `harvest-framing`, `harvest-scout`, `harvest-critique`, `harvest-verify`, `harvest-stitch`, `harvest-atoms`, `gate`, `verification-queue`, `probe`, `query`, `tripwires-list`, `tripwire-fire`, `stitch-brief`, `farm-outcome`, `persona-swap-prepare`, `persona-swap-write`, `map-write` (Task 9 adds `materialize`). All take `--corpus DIR` (default `corpus`) and, where they read a payload, `--input PATH` (`-` = stdin)
- Produces (helpers): `helpers.framing_fixture() -> dict`, `helpers.scout_fixture(round, decision, **overrides) -> dict`, `helpers.critique_fixture() -> dict` — canonical pipeline payloads shared by `test_cli`, `test_materialize`

Event file labels written by the CLI (chronological within a run dir): `p0-sentinel`, `p1-framing`, `p1-farm{F}-init`, `p2-farm{F}-r{NN}`, `p2z-farm{F}-outcome`, `p3-farm{F}-r{NN}`, `p4-verify`, `p5-stitch`, `p6-{farm}`, `p7-materialize`. (`p2z…` sorts after every `p2-farm{F}-rNN` file and before `p3…` because `-` orders before `z` and `2z` before `3` — the reducer replays in sorted path order.)

Design notes locked here:
- `farm-init` **re-observes the farm's hypothesis node with the farm's own vantage** (a `node` event in `p1-farm{F}-init.jsonl`). This makes the hypothesis one of the farm's atoms, so critique edges against it (including the premortem) block that farm's CONCLUDE gate until sublated.
- `gate` is called **after** `harvest-scout` (which appends the round's triggers and ledger entry), so the gate sees the cumulative record.
- `farm-outcome --decision CONCEDE` also appends a `status` event marking the farm's hypothesis `conceded` with its `died_because` (spec §4.2: conceded hypotheses stay on the map with their died-because record). CONCLUDE and ELEVATE change no node status.
- `query` returns `[]` when the chroma store doesn't exist yet (before the first materialize) — first-run scouts simply get an empty warm start.

- [ ] **Step 1: Append embedding utilities to `src/antfarm/cluster.py`**

Add `import hashlib`, `import json`, and `from pathlib import Path` to the imports, then append:

```python
def hash_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic 256-dim hashed word unigram+bigram embedding. For tests and
    offline smoke runs (ANTFARM_EMBED=hash) - not a semantic model. Word grams in
    256 dims keep distinct sentences well below the 0.67 entailment threshold
    (char trigrams did not: nearly all English pairs merged)."""
    out = []
    for text in texts:
        vec = [0.0] * 256
        words = text.lower().split()
        grams = words + [f"{a} {b}" for a, b in zip(words, words[1:], strict=False)]
        for gram in grams:
            digest = hashlib.sha256(gram.encode()).digest()
            vec[int.from_bytes(digest[:2], "big") % 256] += 1.0
        out.append(vec)
    return out


class CachedEmbed:
    """File-backed embedding cache keyed by text hash, so repeated CLI
    invocations (gate, probe, materialize) don't re-embed the whole corpus."""

    def __init__(self, path: Path, base: EmbedFn):
        self.path = path
        self.base = base
        self._cache: dict[str, list[float]] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {})

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:24]

    def __call__(self, texts: list[str]) -> list[list[float]]:
        missing = [t for t in texts if self._key(t) not in self._cache]
        if missing:
            for text, vec in zip(missing, self.base(missing), strict=True):
                self._cache[self._key(text)] = vec
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._cache), encoding="utf-8")
        return [self._cache[self._key(t)] for t in texts]
```

Add a quick test to `tests/test_cluster.py`:

```python
def test_hash_embed_deterministic_discriminative_and_cached(tmp_path):
    from antfarm.cluster import CachedEmbed, cosine, hash_embed

    a = hash_embed(["storage lags panels"])
    assert a == hash_embed(["storage lags panels"])
    # identical text scores 1.0; distinct sentences stay below the 0.67 threshold
    pair = hash_embed(["Storage constraints bind solar growth through 2030.",
                       "No single constraint binds solar growth through 2030."])
    assert cosine(pair[0], pair[0]) == pytest.approx(1.0)
    assert cosine(pair[0], pair[1]) < 0.67

    calls = []

    def counting(texts):
        calls.append(list(texts))
        return hash_embed(texts)

    cached = CachedEmbed(tmp_path / "cache.json", counting)
    first = cached(["one text", "two text"])
    second = cached(["one text", "two text"])
    assert first == second and len(calls) == 1
    # a fresh instance reads the file, no base calls
    reloaded = CachedEmbed(tmp_path / "cache.json", counting)
    assert reloaded(["one text"]) == [first[0]] and len(calls) == 1
```

Run: `uv run pytest tests/test_cluster.py -v` — Expected: 6 passed, 1 deselected

- [ ] **Step 2: Append shared pipeline fixtures to `tests/helpers.py`**

```python
HYPOTHESIS_TEXT = "Storage constraints bind solar growth through 2030."
NULL_TEXT = "No single constraint binds solar growth through 2030."
CLAIM_TEXT = "Grid storage lags panel deployment by several years."
CRITIQUE_TEXT = "Storage-lag statistics conflate contracted and installed capacity."
PREMORTEM_TEXT = "The storage thesis failed by 2027 because interconnection queues cleared."
REBUT_CRITIQUE = "Contracted-capacity inflation is corrected in the dataset revision."
REBUT_PREMORTEM = "Interconnection queue reform bills stalled in every 2025 session."
TRIGGER_TEXT = "A 2027 storage glut with flat solar growth falsifies the storage thesis."


def framing_fixture() -> dict:
    return {
        "stasis": "quality", "altitude": "market-level, 5-year horizon",
        "dissolve": {"dissolved": False, "diagnosis": None, "replacement_question": None},
        "reference_class": "infrastructure cost-decline theses",
        "base_rate": "roughly half survive a decade",
        "zwicky_dimensions": [{"name": "constraint", "values": ["storage", "grid", "none"]}],
        "incoherent_cells": [],
        "rivals": [{"text": HYPOTHESIS_TEXT, "is_null": False, "warm_started": False},
                   {"text": NULL_TEXT, "is_null": True, "warm_started": False}],
    }


def scout_fixture(round: int, decision: str, **overrides) -> dict:
    base = {
        "sublation": [], "expansion": f"Round {round} expansion of the storage thesis.",
        "atoms": [{"type": "claim", "text": CLAIM_TEXT,
                   "strength": None, "diagnosticity": None}],
        "edges": [],
        "falsification_triggers": [],
        "compressed_state": f"Thesis after round {round}: storage binds growth.",
        "confidence_r": "med", "confidence_c": "med",
        "ledger_entry": None, "decision": decision, "died_because": None,
    }
    if round >= 2:
        base["sublation"] = [
            {"critique": CRITIQUE_TEXT, "disposition": "rebutted",
             "response": REBUT_CRITIQUE},
            {"critique": PREMORTEM_TEXT, "disposition": "rebutted",
             "response": REBUT_PREMORTEM}]
        base["atoms"] = [{"type": "claim", "text": REBUT_CRITIQUE,
                          "strength": None, "diagnosticity": None},
                         {"type": "claim", "text": REBUT_PREMORTEM,
                          "strength": None, "diagnosticity": None}]
        base["edges"] = [{"src": REBUT_CRITIQUE, "dst": CRITIQUE_TEXT,
                          "rel": "rebuts", "warrant": None},
                         {"src": REBUT_PREMORTEM, "dst": PREMORTEM_TEXT,
                          "rel": "rebuts", "warrant": None}]
        base["falsification_triggers"] = [{"text": TRIGGER_TEXT, "severity": "high"}]
        base["ledger_entry"] = {"trigger": "round 1 critique",
                                "change": "rebutted both challenges",
                                "novel_content": True}
    return {**base, **overrides}


def critique_fixture() -> dict:
    return {
        "findings": [{"target_text": CLAIM_TEXT, "kind": "warrant_probe",
                      "classification": "undercutting", "severity": "high",
                      "text": CRITIQUE_TEXT}],
        "premortem": PREMORTEM_TEXT,
        "summary": "One HIGH warrant probe; premortem names interconnection risk.",
    }
```

- [ ] **Step 3: Write the failing test**

`tests/test_cli.py`:

```python
import json

import pytest
from helpers import (
    CLAIM_TEXT,
    HYPOTHESIS_TEXT,
    critique_fixture,
    framing_fixture,
    scout_fixture,
)

from antfarm.cli import main
from antfarm.emission import export_schemas

QUESTION = "What limits US solar growth through 2030?"


@pytest.fixture(autouse=True)
def _offline_embeddings(monkeypatch):
    monkeypatch.setenv("ANTFARM_EMBED", "hash")


@pytest.fixture()
def corpus_dir(tmp_path):
    return tmp_path / "corpus"


def run_cli(corpus_dir, *argv, payload=None):
    args = list(argv) + ["--corpus", str(corpus_dir)]
    if payload is not None:
        path = corpus_dir.parent / "payload.json"
        path.write_text(json.dumps(payload))
        args += ["--input", str(path)]
    return main(args)


def test_schemas_matches_export(corpus_dir, capsys):
    result = run_cli(corpus_dir, "schemas")
    assert result == export_schemas()
    assert json.loads(capsys.readouterr().out) == result


def test_run_new_binds_question_and_increments(corpus_dir):
    first = run_cli(corpus_dir, "run-new", "--question", QUESTION)
    assert first == {"run": "r0001", "question_id": first["question_id"],
                     "first_run": True}
    second = run_cli(corpus_dir, "run-new", "--question", QUESTION)
    assert second["run"] == "r0002" and second["first_run"] is False
    with pytest.raises(SystemExit):
        run_cli(corpus_dir, "run-new", "--question", "A different question entirely?")


def _start_farm(corpus_dir):
    run = run_cli(corpus_dir, "run-new", "--question", QUESTION)["run"]
    harvested = run_cli(corpus_dir, "harvest-framing", "--run", run,
                        payload=framing_fixture())
    rival = harvested["rivals"][0]
    run_cli(corpus_dir, "farm-init", "--run", run, "--farm", "A",
            "--hypothesis-id", rival["id"], "--hypothesis-text", rival["text"],
            "--persona", "a municipal procurement officer", "--family", "opus")
    return run, rival


def test_full_farm_round_trip_gates_conclude(corpus_dir):
    run, rival = _start_farm(corpus_dir)

    r1 = scout_fixture(1, "CONTINUE")
    h1 = run_cli(corpus_dir, "harvest-scout", "--run", run, "--farm", "A",
                 "--round", "1", "--family", "opus", "--persona", "officer",
                 payload=r1)
    assert h1["atom_ids"] and not h1["rejected"]
    gate1 = run_cli(corpus_dir, "gate", "--run", run, "--farm", "A", payload=r1)
    assert gate1["decision"] == "CONTINUE"

    run_cli(corpus_dir, "harvest-critique", "--run", run, "--farm", "A",
            "--round", "1", payload=critique_fixture())
    # premature CONCLUDE now blocks: standing undercutters + no HIGH trigger yet
    blocked = run_cli(corpus_dir, "gate", "--run", run, "--farm", "A",
                      payload=scout_fixture(1, "CONCLUDE"))
    assert blocked["decision"] == "CONTINUE" and blocked["forced"]

    r2 = scout_fixture(2, "CONCLUDE")
    run_cli(corpus_dir, "harvest-scout", "--run", run, "--farm", "A",
            "--round", "2", "--family", "opus", "--persona", "officer", payload=r2)
    gate2 = run_cli(corpus_dir, "gate", "--run", run, "--farm", "A", payload=r2)
    assert gate2 == {"decision": "CONCLUDE", "forced": False, "reasons": []}
    run_cli(corpus_dir, "farm-outcome", "--run", run, "--farm", "A",
            "--decision", "CONCLUDE")

    queue = run_cli(corpus_dir, "verification-queue")
    assert any(q["text"] == CLAIM_TEXT for q in queue)
    claim_id = next(q["id"] for q in queue if q["text"] == CLAIM_TEXT)
    verified = run_cli(corpus_dir, "harvest-verify", "--run", run, payload=[
        {"atom_id": claim_id, "verified": True,
         "evidence": "CAISO reports corroborate.", "source": "caiso.com"}])
    assert verified["verified"] == [claim_id]


def test_probe_and_query_before_first_materialize(corpus_dir):
    run, rival = _start_farm(corpus_dir)
    dup = run_cli(corpus_dir, "probe", payload={"text": HYPOTHESIS_TEXT})
    assert dup["novel"] is False
    novel = run_cli(corpus_dir, "probe",
                    payload={"text": "zqx wvj kkp qqe zzt xxr wwy vvu"})
    assert novel["novel"] is True
    hits = run_cli(corpus_dir, "query", "--collection", "view", "--text", "storage")
    assert hits == []  # no chroma store before first materialize


def test_stitch_and_tripwire_flow(corpus_dir):
    run, rival = _start_farm(corpus_dir)
    run_cli(corpus_dir, "harvest-scout", "--run", run, "--farm", "A", "--round", "2",
            "--family", "opus", "--persona", "officer",
            payload=scout_fixture(2, "CONCLUDE"))
    stitch = {
        "ach": [], "investigations": [],
        "declaration_kind": "basin",
        "declaration_summary": "Storage thesis holds.",
        "positions": [{"hypothesis_text": HYPOTHESIS_TEXT, "condition": None}],
        "dissolve": {"dissolved": False, "diagnosis": None, "replacement_question": None},
    }
    result = run_cli(corpus_dir, "harvest-stitch", "--run", run, payload=stitch)
    assert result["declaration"]["kind"] == "basin"
    assert "e_band" in result["declaration"]
    declaration_path = corpus_dir / "runs" / run / "declaration.json"
    assert declaration_path.exists()
    brief = run_cli(corpus_dir, "stitch-brief", "--run", run)
    assert brief["farms"][0]["farm"] == "A"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'antfarm.cli'`

- [ ] **Step 5: Write the implementation**

`src/antfarm/__main__.py`:

```python
from antfarm.cli import main

if __name__ == "__main__":
    main()
```

`src/antfarm/cli.py`:

```python
"""The survey pipeline's only door into the corpus. One subcommand per
deterministic step; JSON in (--input), one JSON object out (stdout). The
workflow's clerk agent runs these commands; nothing else writes events."""

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from antfarm import brief as brief_mod
from antfarm import farm as farm_mod
from antfarm.analysis import ach_winner, derive_e
from antfarm.cluster import CachedEmbed, EmbeddingMatcher, EmbedFn, hash_embed
from antfarm.counterfactual import persona_swap, regenerated_to_turns, swap_package
from antfarm.emission import (
    AtomBatch,
    CritiqueReport,
    CuratorOutput,
    FramingOutput,
    PersonaSwapOutput,
    ScoutRoundOutput,
    StitchOutput,
    VerificationResult,
    export_schemas,
)
from antfarm.events import append_events, read_events, status_event
from antfarm.gates import resolve_decision
from antfarm.graph import build_graph, compute_centrality, extract_cruxes
from antfarm.harvest import (
    batch_harvest,
    critique_harvest,
    framing_harvest,
    scout_harvest,
    stitch_harvest,
    verify_harvest,
)
from antfarm.reduce import Corpus, reduce_events
from antfarm.schema import Vantage, normalize_text
from antfarm.stores import CorpusStore
from antfarm.tripwires import fire_tripwire, standing_tripwires


def now_ts() -> str:
    return datetime.now(UTC).isoformat()


def question_id_for(text: str) -> str:
    digest = hashlib.sha256(f"question:{normalize_text(text)}".encode()).hexdigest()
    return f"q-{digest[:12]}"


def get_embed(corpus_dir: Path) -> EmbedFn:
    cache = corpus_dir / "emb-cache.json"
    if os.environ.get("ANTFARM_EMBED") == "hash":
        return CachedEmbed(cache, hash_embed)
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    ef = DefaultEmbeddingFunction()

    def chroma_embed(texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in ef(texts)]

    return CachedEmbed(cache, chroma_embed)


def load_corpus(corpus_dir: Path) -> Corpus:
    runs_root = corpus_dir / "runs"
    if not runs_root.exists():
        return Corpus()
    return reduce_events(read_events(runs_root),
                         matcher=EmbeddingMatcher(get_embed(corpus_dir)))


def read_payload(args: argparse.Namespace) -> Any:
    raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(
        encoding="utf-8")
    return json.loads(raw)


def stored_question(corpus_dir: Path) -> dict:
    path = corpus_dir / "question.json"
    if not path.exists():
        raise SystemExit("no question bound to this corpus - run `run-new` first")
    return json.loads(path.read_text(encoding="utf-8"))


def _vantage(run: str, farm: str, family: str, persona: str, round: int,
             sensor: str = "model") -> Vantage:
    return Vantage(run=run, farm=farm, family=family, persona=persona,
                   round=round, sensor=sensor)


# --- handlers ---------------------------------------------------------------


def cmd_schemas(args: argparse.Namespace) -> dict:
    return export_schemas()


def cmd_run_new(args: argparse.Namespace) -> dict:
    corpus_dir: Path = args.corpus
    qid = question_id_for(args.question)
    qfile = corpus_dir / "question.json"
    if qfile.exists():
        stored = json.loads(qfile.read_text(encoding="utf-8"))
        if stored["question_id"] != qid:
            raise SystemExit(
                f"corpus is bound to question {stored['question_id']} "
                f"({stored['text']!r}); one corpus dir per question")
    else:
        corpus_dir.mkdir(parents=True, exist_ok=True)
        qfile.write_text(json.dumps({"question_id": qid, "text": args.question}),
                         encoding="utf-8")
    runs_root = corpus_dir / "runs"
    existing = sorted(runs_root.glob("r[0-9]*")) if runs_root.exists() else []
    run = f"r{len(existing) + 1:04d}"
    (runs_root / run).mkdir(parents=True, exist_ok=True)
    return {"run": run, "question_id": qid, "first_run": not existing}


def cmd_brief(args: argparse.Namespace) -> dict:
    question = stored_question(args.corpus)
    corpus = load_corpus(args.corpus)
    return brief_mod.warm_brief(corpus, question["question_id"], args.corpus / "runs")


def cmd_farm_init(args: argparse.Namespace) -> dict:
    question = stored_question(args.corpus)
    meta = farm_mod.FarmMeta(
        farm=args.farm, hypothesis_id=args.hypothesis_id,
        hypothesis_text=args.hypothesis_text, persona=args.persona,
        family=args.family, question_id=question["question_id"],
        question_text=question["text"])
    farm_mod.init_farm(args.corpus, args.run, args.farm, meta)
    # re-observe the hypothesis under the farm's vantage so critiques against it
    # (incl. the premortem) block THIS farm's CONCLUDE gate until sublated
    vantage = _vantage(args.run, args.farm, args.family, args.persona, round=1)
    batch = AtomBatch(atoms=[{"type": "hypothesis", "text": args.hypothesis_text}])
    result = batch_harvest(batch, vantage=vantage, corpus=Corpus(),
                           question_id=question["question_id"], ts=now_ts())
    append_events(args.corpus / "runs" / args.run, f"p1-farm{args.farm}-init",
                  result.events)
    return {"farm": args.farm, "hypothesis_id": args.hypothesis_id}


def cmd_harvest_framing(args: argparse.Namespace) -> dict:
    question = stored_question(args.corpus)
    output = FramingOutput.model_validate(read_payload(args))
    vantage = _vantage(args.run, "surveyor", "session", "surveyor", round=0)
    result, rivals = framing_harvest(output, vantage=vantage,
                                     question_id=question["question_id"], ts=now_ts())
    run_dir = args.corpus / "runs" / args.run
    if result.events:
        append_events(run_dir, "p1-framing", result.events)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "framing.json").write_text(output.model_dump_json(indent=2),
                                          encoding="utf-8")
    return {"rivals": rivals, "dissolved": output.dissolve.dissolved,
            "rejected": result.rejected}


def cmd_harvest_scout(args: argparse.Namespace) -> dict:
    question = stored_question(args.corpus)
    output = ScoutRoundOutput.model_validate(read_payload(args))
    corpus = load_corpus(args.corpus)
    d = farm_mod.farm_dir(args.corpus, args.run, args.farm)
    vantage = _vantage(args.run, args.farm, args.family, args.persona, args.round)
    result = scout_harvest(output, vantage=vantage, corpus=corpus,
                           question_id=question["question_id"], ts=now_ts(),
                           start_turn=farm_mod.next_turn_index(d))
    append_events(args.corpus / "runs" / args.run,
                  f"p2-farm{args.farm}-r{args.round:02d}", result.events)
    farm_mod.append_turns(d, result.turns)
    if output.falsification_triggers:
        farm_mod.append_triggers(d, output.falsification_triggers)
    if output.ledger_entry is not None:
        farm_mod.append_ledger(d, output.ledger_entry)
    return {"atom_ids": result.atom_ids, "rejected": result.rejected,
            "unresolved": result.unresolved, "turns_appended": len(result.turns)}


def cmd_harvest_critique(args: argparse.Namespace) -> dict:
    question = stored_question(args.corpus)
    report = CritiqueReport.model_validate(read_payload(args))
    corpus = load_corpus(args.corpus)
    d = farm_mod.farm_dir(args.corpus, args.run, args.farm)
    meta = farm_mod.read_meta(d)
    vantage = _vantage(args.run, args.farm, args.family, "blind-critic", args.round)
    result = critique_harvest(report, vantage=vantage, corpus=corpus,
                              hypothesis_id=meta.hypothesis_id,
                              question_id=question["question_id"], ts=now_ts(),
                              start_turn=farm_mod.next_turn_index(d))
    append_events(args.corpus / "runs" / args.run,
                  f"p3-farm{args.farm}-r{args.round:02d}", result.events)
    farm_mod.append_turns(d, result.turns)
    farm_mod.write_critique(d, args.round, report)
    return {"atom_ids": result.atom_ids, "rejected": result.rejected,
            "unresolved": result.unresolved}


def cmd_harvest_verify(args: argparse.Namespace) -> dict:
    results = TypeAdapter(list[VerificationResult]).validate_python(read_payload(args))
    corpus = load_corpus(args.corpus)
    vantage = _vantage(args.run, "verifier", "session", "verifier", round=0)
    result = verify_harvest(results, corpus=corpus, vantage=vantage, ts=now_ts())
    if result.events:
        append_events(args.corpus / "runs" / args.run, "p4-verify", result.events)
    return {"verified": result.atom_ids, "unresolved": result.unresolved}


def cmd_harvest_stitch(args: argparse.Namespace) -> dict:
    question = stored_question(args.corpus)
    output = StitchOutput.model_validate(read_payload(args))
    corpus = load_corpus(args.corpus)
    vantage = _vantage(args.run, "stitcher", "session", "stitcher", round=0)
    result = stitch_harvest(output, vantage=vantage, corpus=corpus,
                            question_id=question["question_id"], ts=now_ts())
    if result.events:
        append_events(args.corpus / "runs" / args.run, "p5-stitch", result.events)
    after = load_corpus(args.corpus)
    cent = compute_centrality(build_graph(after))
    declaration = {
        "kind": output.declaration_kind,
        "summary": output.declaration_summary,
        "positions": [p.model_dump() for p in output.positions],
        "dissolved": output.dissolve.dissolved,
        "ach": ach_winner(after, question["question_id"]),
        "e_band": derive_e(after, question["question_id"]),
        "cruxes": [{"id": nid, "text": after.nodes[nid].text}
                   for nid in extract_cruxes(after, cent)],
    }
    (args.corpus / "runs" / args.run / "declaration.json").write_text(
        json.dumps(declaration, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"declaration": declaration, "rejected": result.rejected,
            "unresolved": result.unresolved}


def cmd_harvest_atoms(args: argparse.Namespace) -> dict:
    question = stored_question(args.corpus)
    batch = AtomBatch.model_validate(read_payload(args))
    corpus = load_corpus(args.corpus)
    vantage = _vantage(args.run, args.farm, args.family, args.persona, args.round,
                       sensor=args.sensor)
    result = batch_harvest(batch, vantage=vantage, corpus=corpus,
                           question_id=question["question_id"], ts=now_ts())
    if result.events:
        append_events(args.corpus / "runs" / args.run, f"p6-{args.farm}", result.events)
    return {"atom_ids": result.atom_ids, "rejected": result.rejected,
            "unresolved": result.unresolved}


def cmd_gate(args: argparse.Namespace) -> dict:
    output = ScoutRoundOutput.model_validate(read_payload(args))
    corpus = load_corpus(args.corpus)
    d = farm_mod.farm_dir(args.corpus, args.run, args.farm)
    result = resolve_decision(
        scout_decision=output.decision, corpus=corpus, farm=args.farm,
        triggers=farm_mod.read_triggers(d), ledger=farm_mod.read_ledger(d),
        final_round=args.final_round)
    return result.model_dump()


def cmd_verification_queue(args: argparse.Namespace) -> list[dict]:
    return brief_mod.verification_queue(load_corpus(args.corpus))


def cmd_probe(args: argparse.Namespace) -> dict:
    payload = read_payload(args)
    corpus = load_corpus(args.corpus)
    return brief_mod.probe(corpus, get_embed(args.corpus), payload["text"])


def cmd_query(args: argparse.Namespace) -> list[dict]:
    chroma_dir = args.corpus / "chroma"
    if not chroma_dir.exists():
        return []
    store = CorpusStore.persistent(chroma_dir, get_embed(args.corpus))
    try:
        return store.query(args.collection, args.text, n=args.n)
    except Exception:  # collection missing before first materialize
        return []


def cmd_tripwires_list(args: argparse.Namespace) -> list[dict]:
    return standing_tripwires(load_corpus(args.corpus))


def cmd_tripwire_fire(args: argparse.Namespace) -> dict:
    payload = read_payload(args)
    question = stored_question(args.corpus)
    corpus = load_corpus(args.corpus)
    vantage = _vantage(args.run, "sentinel", "session", "sentinel", round=0)
    events, affected = fire_tripwire(corpus, args.id, payload["evidence"],
                                     vantage=vantage,
                                     question_id=question["question_id"], ts=now_ts())
    append_events(args.corpus / "runs" / args.run, "p0-sentinel", events)
    return {"affected": affected}


def cmd_stitch_brief(args: argparse.Namespace) -> dict:
    return brief_mod.stitch_brief(load_corpus(args.corpus), args.corpus, args.run)


def cmd_farm_outcome(args: argparse.Namespace) -> dict:
    d = farm_mod.farm_dir(args.corpus, args.run, args.farm)
    farm_mod.write_outcome(d, args.decision, args.died_because)
    if args.decision == "CONCEDE":
        meta = farm_mod.read_meta(d)
        append_events(args.corpus / "runs" / args.run, f"p2z-farm{args.farm}-outcome",
                      [status_event(meta.hypothesis_id, "conceded", ts=now_ts(),
                                    died_because=args.died_because)])
    return {"farm": args.farm, "decision": args.decision}


def cmd_persona_swap_prepare(args: argparse.Namespace) -> dict:
    d = farm_mod.farm_dir(args.corpus, args.run, args.farm)
    return swap_package(farm_mod.read_turns(d), args.start_iteration)


def cmd_persona_swap_write(args: argparse.Namespace) -> dict:
    output = PersonaSwapOutput.model_validate(read_payload(args))
    d = farm_mod.farm_dir(args.corpus, args.run, args.farm)
    host = farm_mod.read_turns(d)
    swapped = persona_swap(host, regenerated_to_turns(output), args.start_iteration)
    out_dir = args.corpus / "exports" / args.run / f"{args.farm}-persona-swap"
    out_dir.mkdir(parents=True, exist_ok=True)
    trace = out_dir / "trace.jsonl"
    with trace.open("w", encoding="utf-8") as f:
        for t in swapped:
            f.write(t.model_dump_json() + "\n")
    (out_dir / "stats.json").write_text(json.dumps({
        "counterfactual": "persona_swap",
        "start_iteration": args.start_iteration,
        "turns": len(swapped)}), encoding="utf-8")
    return {"trace": str(trace), "turns": len(swapped)}


def cmd_map_write(args: argparse.Namespace) -> dict:
    output = CuratorOutput.model_validate(read_payload(args))
    vault = args.corpus / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    path = vault / "MAP.md"
    path.write_text(output.map_markdown, encoding="utf-8")
    return {"path": str(path)}


HANDLERS = {
    "schemas": cmd_schemas,
    "run-new": cmd_run_new,
    "brief": cmd_brief,
    "farm-init": cmd_farm_init,
    "harvest-framing": cmd_harvest_framing,
    "harvest-scout": cmd_harvest_scout,
    "harvest-critique": cmd_harvest_critique,
    "harvest-verify": cmd_harvest_verify,
    "harvest-stitch": cmd_harvest_stitch,
    "harvest-atoms": cmd_harvest_atoms,
    "gate": cmd_gate,
    "verification-queue": cmd_verification_queue,
    "probe": cmd_probe,
    "query": cmd_query,
    "tripwires-list": cmd_tripwires_list,
    "tripwire-fire": cmd_tripwire_fire,
    "stitch-brief": cmd_stitch_brief,
    "farm-outcome": cmd_farm_outcome,
    "persona-swap-prepare": cmd_persona_swap_prepare,
    "persona-swap-write": cmd_persona_swap_write,
    "map-write": cmd_map_write,
}


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--corpus", type=Path, default=Path("corpus"))
    common.add_argument("--input", default="-")

    parser = argparse.ArgumentParser(prog="antfarm")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add(name: str, **flags: dict) -> None:
        sp = sub.add_parser(name, parents=[common])
        for flag, kw in flags.items():
            sp.add_argument(flag, **kw)

    add("schemas")
    add("run-new", **{"--question": {"required": True}})
    add("brief")
    add("farm-init", **{"--run": {"required": True}, "--farm": {"required": True},
                        "--hypothesis-id": {"required": True},
                        "--hypothesis-text": {"required": True},
                        "--persona": {"required": True}, "--family": {"required": True}})
    add("harvest-framing", **{"--run": {"required": True}})
    add("harvest-scout", **{"--run": {"required": True}, "--farm": {"required": True},
                            "--round": {"required": True, "type": int},
                            "--family": {"required": True},
                            "--persona": {"required": True}})
    add("harvest-critique", **{"--run": {"required": True}, "--farm": {"required": True},
                               "--round": {"required": True, "type": int},
                               "--family": {"default": "session"}})
    add("harvest-verify", **{"--run": {"required": True}})
    add("harvest-stitch", **{"--run": {"required": True}})
    add("harvest-atoms", **{"--run": {"required": True}, "--farm": {"required": True},
                            "--round": {"default": 0, "type": int},
                            "--family": {"default": "session"},
                            "--persona": {"required": True},
                            "--sensor": {"default": "model",
                                         "choices": ["model", "human"]}})
    add("gate", **{"--run": {"required": True}, "--farm": {"required": True},
                   "--final-round": {"action": "store_true"}})
    add("verification-queue")
    add("probe")
    add("query", **{"--collection": {"required": True}, "--text": {"required": True},
                    "--n": {"default": 8, "type": int}})
    add("tripwires-list")
    add("tripwire-fire", **{"--run": {"required": True}, "--id": {"required": True}})
    add("stitch-brief", **{"--run": {"required": True}})
    add("farm-outcome", **{"--run": {"required": True}, "--farm": {"required": True},
                           "--decision": {"required": True},
                           "--died-because": {"default": None}})
    add("persona-swap-prepare", **{"--run": {"required": True},
                                   "--farm": {"required": True},
                                   "--start-iteration": {"required": True, "type": int}})
    add("persona-swap-write", **{"--run": {"required": True},
                                 "--farm": {"required": True},
                                 "--start-iteration": {"required": True, "type": int}})
    add("map-write")
    return parser


def main(argv: list[str] | None = None) -> Any:
    args = build_parser().parse_args(argv)
    result = HANDLERS[args.cmd](args)
    print(json.dumps(result, ensure_ascii=False))
    return result
```

(Note: `HANDLERS` maps to functions returning `dict` or `list[dict]`; annotate as `dict[str, Callable[[argparse.Namespace], Any]]` if mypy complains. `cmd_query`'s broad `except Exception` is deliberate — a missing collection is an expected pre-materialize state, and chroma's missing-collection exception class varies by version.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: 5 passed

Run the whole suite: `uv run pytest -v`
Expected: all pass, eval deselected

- [ ] **Step 7: Commit**

```bash
uv run ruff check src tests && uv run mypy src
git add src/antfarm/cli.py src/antfarm/__main__.py src/antfarm/cluster.py tests/test_cli.py tests/test_cluster.py tests/helpers.py
git commit -m "feat: python -m antfarm CLI - the workflow's only door into the corpus"
```

---

### Task 9: Materialize — Phase 7 in one command

Rebuilds the derived world from the event log: view gate, chroma stores, Obsidian render, keel transcript exports with outcome labels, and tripwire registration from the run's HIGH-severity falsification triggers.

**Files:**
- Create: `src/antfarm/materialize.py`
- Modify: `src/antfarm/cli.py` (add `materialize` subcommand)
- Test: `tests/test_materialize.py`

**Interfaces:**
- Consumes: everything already built — `reduce_events`/`read_events`/`append_events`, `EmbeddingMatcher`, `build_graph`/`compute_centrality`/`compute_view`, `CorpusStore`, `render_obsidian`, `write_transcript`/`Outcome`/`VerificationStats`, `register_tripwires`, `degeneration_forced`, farm-dir readers (Task 7)
- Produces: `materialize(corpus_dir: Path, run: str, embed: EmbedFn, ts: str) -> dict` returning `{"nodes","edges","view_size","pages","farms_exported","tripwires_registered"}`; CLI subcommand `materialize --run RUN`
- **Refuted computation (spec §9.2 label discipline):** a farm exports `refuted=True` iff its outcome decision is CONCLUDE **and** its hypothesis node is no longer `live` — this is what produces `coherence_label: "coherent_refuted"`. CONCEDE farms export as `"conceded"`, never as degraded.

- [ ] **Step 1: Write the failing test**

`tests/test_materialize.py`:

```python
import json

import pytest
from helpers import TRIGGER_TEXT, critique_fixture, framing_fixture, scout_fixture

from antfarm.cli import main

QUESTION = "What limits US solar growth through 2030?"


@pytest.fixture(autouse=True)
def _offline_embeddings(monkeypatch):
    monkeypatch.setenv("ANTFARM_EMBED", "hash")


def run_cli(corpus_dir, *argv, payload=None):
    args = list(argv) + ["--corpus", str(corpus_dir)]
    if payload is not None:
        path = corpus_dir.parent / "payload.json"
        path.write_text(json.dumps(payload))
        args += ["--input", str(path)]
    return main(args)


@pytest.fixture()
def surveyed(tmp_path):
    corpus_dir = tmp_path / "corpus"
    run = run_cli(corpus_dir, "run-new", "--question", QUESTION)["run"]
    rival = run_cli(corpus_dir, "harvest-framing", "--run", run,
                    payload=framing_fixture())["rivals"][0]
    run_cli(corpus_dir, "farm-init", "--run", run, "--farm", "A",
            "--hypothesis-id", rival["id"], "--hypothesis-text", rival["text"],
            "--persona", "officer", "--family", "opus")
    run_cli(corpus_dir, "harvest-scout", "--run", run, "--farm", "A", "--round", "1",
            "--family", "opus", "--persona", "officer",
            payload=scout_fixture(1, "CONTINUE"))
    run_cli(corpus_dir, "harvest-critique", "--run", run, "--farm", "A", "--round", "1",
            payload=critique_fixture())
    run_cli(corpus_dir, "harvest-scout", "--run", run, "--farm", "A", "--round", "2",
            "--family", "opus", "--persona", "officer",
            payload=scout_fixture(2, "CONCLUDE"))
    run_cli(corpus_dir, "farm-outcome", "--run", run, "--farm", "A",
            "--decision", "CONCLUDE")
    queue = run_cli(corpus_dir, "verification-queue")
    run_cli(corpus_dir, "harvest-verify", "--run", run, payload=[
        {"atom_id": q["id"], "verified": True, "evidence": "corroborated",
         "source": None} for q in queue])
    return corpus_dir, run


def test_materialize_builds_view_vault_and_exports(surveyed):
    corpus_dir, run = surveyed
    summary = run_cli(corpus_dir, "materialize", "--run", run)
    assert summary["view_size"] >= 1
    assert summary["pages"] == summary["view_size"]
    assert summary["farms_exported"] == ["A"]
    assert summary["tripwires_registered"] == 1

    trace = corpus_dir / "exports" / run / "A" / "trace.jsonl"
    lines = [json.loads(line) for line in trace.read_text().splitlines()]
    assert all(set(line) == {"turn", "role", "phase", "iteration", "content"}
               for line in lines)
    stats = json.loads((corpus_dir / "exports" / run / "A" / "stats.json").read_text())
    assert stats["coherence_label"] == "coherent"
    assert stats["outcome"]["ledger_clean"] is True
    assert stats["outcome"]["verification"]["atoms_emitted"] >= 3


def test_materialize_registers_high_triggers_as_tripwires(surveyed):
    corpus_dir, run = surveyed
    run_cli(corpus_dir, "materialize", "--run", run)
    tripwires = run_cli(corpus_dir, "tripwires-list")
    assert len(tripwires) == 1 and tripwires[0]["text"] == TRIGGER_TEXT
    assert tripwires[0]["watches"]  # it watches the farm's hypothesis
    # re-materializing must not duplicate the tripwire (content-hash identity)
    run_cli(corpus_dir, "materialize", "--run", run)
    assert len(run_cli(corpus_dir, "tripwires-list")) == 1


def test_materialized_store_answers_queries(surveyed):
    corpus_dir, run = surveyed
    run_cli(corpus_dir, "materialize", "--run", run)
    hits = run_cli(corpus_dir, "query", "--collection", "well",
                   "--text", "storage lags panel deployment")
    assert hits
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_materialize.py -v`
Expected: FAIL with `error: argument cmd: invalid choice: 'materialize'` (or `ModuleNotFoundError` once wired)

- [ ] **Step 3: Write the implementation**

`src/antfarm/materialize.py`:

```python
"""Phase 7: rebuild the derived world from the event log - view gate, chroma
stores, Obsidian render, keel transcript exports, tripwire registration."""

from pathlib import Path

from antfarm.cluster import EmbeddingMatcher, EmbedFn
from antfarm.events import append_events, read_events
from antfarm.farm import read_ledger, read_meta, read_outcome, read_triggers, read_turns
from antfarm.gates import degeneration_forced
from antfarm.graph import build_graph, compute_centrality, compute_view
from antfarm.reduce import Corpus, reduce_events
from antfarm.render import render_obsidian
from antfarm.schema import Vantage
from antfarm.stores import CorpusStore
from antfarm.transcript import Outcome, VerificationStats, write_transcript
from antfarm.tripwires import register_tripwires


def _farm_stats(corpus: Corpus, farm: str) -> VerificationStats:
    emitted = [n for n in corpus.nodes.values()
               if any(v.farm == farm for v in n.vantages)]
    return VerificationStats(atoms_emitted=len(emitted),
                             atoms_verified=sum(1 for n in emitted if n.verified))


def materialize(corpus_dir: Path, run: str, embed: EmbedFn, ts: str) -> dict:
    runs_root = corpus_dir / "runs"
    farms_root = corpus_dir / "farms" / run
    farm_dirs = (sorted(d for d in farms_root.iterdir() if (d / "meta.json").exists())
                 if farms_root.exists() else [])

    # 1. register this run's HIGH-severity falsification triggers as tripwires
    corpus = reduce_events(read_events(runs_root), matcher=EmbeddingMatcher(embed))
    trip_events: list[dict] = []
    for d in farm_dirs:
        meta = read_meta(d)
        vantage = Vantage(run=run, farm=meta.farm, family=meta.family,
                          persona=meta.persona, round=0, sensor="model")
        trip_events.extend(register_tripwires(
            read_triggers(d), meta.hypothesis_id, vantage=vantage,
            question_id=meta.question_id, ts=ts))
    if trip_events:
        append_events(runs_root / run, "p7-materialize", trip_events)
        corpus = reduce_events(read_events(runs_root), matcher=EmbeddingMatcher(embed))

    # 2. view gate, stores, render
    graph = build_graph(corpus)
    cent = compute_centrality(graph)
    view_ids = compute_view(corpus, cent)
    store = CorpusStore.persistent(corpus_dir / "chroma", embed)
    store.rebuild(corpus, view_ids)
    pages = render_obsidian(corpus, view_ids, corpus_dir / "vault")

    # 3. keel transcript exports (spec §4.5, §9.2)
    exported = []
    for d in farm_dirs:
        meta = read_meta(d)
        turns = read_turns(d)
        ledger = read_ledger(d)
        stored = read_outcome(d) or {"decision": "ELEVATE", "died_because": None}
        hypothesis = corpus.nodes.get(meta.hypothesis_id)
        refuted = (stored["decision"] == "CONCLUDE"
                   and hypothesis is not None and hypothesis.status != "live")
        outcome = Outcome(decision=stored["decision"], ledger=ledger,
                          ledger_clean=not degeneration_forced(ledger),
                          verification=_farm_stats(corpus, meta.farm),
                          refuted=refuted, died_because=stored.get("died_because"))
        last_round = max((t.iteration for t in turns), default=1)
        vantage = Vantage(run=run, farm=meta.farm, family=meta.family,
                          persona=meta.persona, round=last_round, sensor="model")
        write_transcript(corpus_dir / "exports" / run / meta.farm, turns, vantage,
                         outcome)
        exported.append(meta.farm)

    return {"nodes": len(corpus.nodes), "edges": len(corpus.edges),
            "view_size": len(view_ids), "pages": len(pages),
            "farms_exported": exported,
            "tripwires_registered": sum(1 for e in trip_events if e["kind"] == "node")}
```

Wire into `src/antfarm/cli.py`:

```python
from antfarm.materialize import materialize


def cmd_materialize(args: argparse.Namespace) -> dict:
    return materialize(args.corpus, args.run, get_embed(args.corpus), now_ts())
```

add to `HANDLERS`: `"materialize": cmd_materialize,` and to `build_parser()`:

```python
    add("materialize", **{"--run": {"required": True}})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_materialize.py -v`
Expected: 3 passed

Run: `uv run pytest -v`
Expected: full suite passes

- [ ] **Step 5: Commit**

```bash
uv run ruff check src tests && uv run mypy src
git add src/antfarm/materialize.py src/antfarm/cli.py tests/test_materialize.py
git commit -m "feat: materialize - view, stores, vault, keel exports, tripwire registration"
```

---

### Task 10: The agent definitions

> **Amended 2026-07-05 (mid-execution, before this task started):** the agent files are thin routers; the proven pass content from dialectic-plugin v1 is PORTED into reference files, not re-derived. Spec §9.1 mandates "kept and sharpened" — a 50-line from-scratch prompt discards prompt content already proven to improve reasoning (meta-probes, preservation gate, elevation test, evidence gates, fact-check protocol, worked examples). Step 4 below is the port; scout and blind-critic Read their pass files at runtime.

Eight files under `.claude/agents/`: the seven survey roles (spec §3) plus the mechanical clerk. These are consumed by `agent(..., {agentType: '<name>'})` in the workflow. Keep each under ~50 lines; iron laws in the first lines (primacy bias, spec §9.1 style rules). The agent `.md` is the router; depth lives in `.claude/skills/survey/references/` (hub-and-spoke, spec §9.1).

**Files:**
- Create: `.claude/agents/surveyor.md`, `.claude/agents/scout.md`, `.claude/agents/blind-critic.md`, `.claude/agents/hole-finder.md`, `.claude/agents/stitcher.md`, `.claude/agents/sentinel.md`, `.claude/agents/curator.md`, `.claude/agents/clerk.md`
- Create: `.claude/skills/survey/references/expansion.md`, `.claude/skills/survey/references/compression.md`, `.claude/skills/survey/references/sublation-and-decision.md`, `.claude/skills/survey/references/critique-probes.md` (ported — see Step 4)
- Source (read-only, sibling repo): `../dialectic-plugin/skills/dialectic/{EXPANSION,COMPRESSION,CRITIQUE,MARKERS}.md`
- Test: `tests/test_agents.py`

**Interfaces:**
- Consumes: the proven dialectic v1 pass files named above (prose only)
- Produces: agent types `surveyor`, `scout`, `blind-critic`, `hole-finder`, `stitcher`, `sentinel`, `curator`, `clerk` resolvable by the Workflow runtime's `agentType` option; pass reference files Read by scout and blind-critic at runtime

- [ ] **Step 1: Write the failing test**

`tests/test_agents.py`:

```python
from pathlib import Path

AGENTS = ["surveyor", "scout", "blind-critic", "hole-finder", "stitcher",
          "sentinel", "curator", "clerk"]
AGENTS_DIR = Path(__file__).parent.parent / ".claude" / "agents"


def _frontmatter(name: str) -> dict:
    text = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{name}.md missing frontmatter"
    block = text.split("---", 2)[1]
    fields = {}
    for line in block.strip().splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def test_all_agents_exist_with_valid_frontmatter():
    for name in AGENTS:
        fields = _frontmatter(name)
        assert fields["name"] == name
        assert fields["description"]
        assert fields["tools"]


def test_blinding_rules_are_stated():
    critic = (AGENTS_DIR / "blind-critic.md").read_text(encoding="utf-8")
    assert "authorless" in critic or "third-party" in critic
    scout = (AGENTS_DIR / "scout.md").read_text(encoding="utf-8")
    assert "view" in scout and "well" in scout  # routing rule is written down


REFERENCES = ["expansion", "compression", "sublation-and-decision", "critique-probes"]
REFS_DIR = Path(__file__).parent.parent / ".claude" / "skills" / "survey" / "references"


def test_pass_reference_files_are_ported_not_stubbed():
    for name in REFERENCES:
        text = (REFS_DIR / f"{name}.md").read_text(encoding="utf-8")
        assert len(text.splitlines()) >= 60, f"{name}.md looks stubbed - port the source content"


def test_routers_point_at_their_pass_files():
    scout = (AGENTS_DIR / "scout.md").read_text(encoding="utf-8")
    for name in ("expansion", "compression", "sublation-and-decision"):
        assert f"references/{name}.md" in scout, f"scout.md must route to {name}.md"
    critic = (AGENTS_DIR / "blind-critic.md").read_text(encoding="utf-8")
    assert "references/critique-probes.md" in critic
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agents.py -v`
Expected: FAIL with `FileNotFoundError`

- [ ] **Step 3: Write the agent definitions**

`.claude/agents/clerk.md`:

```markdown
---
name: clerk
description: Mechanical command runner for the survey workflow. Executes exactly the CLI commands given in the prompt and returns their output. Never reasons about the survey question.
tools: Bash, Read, Write
---

You execute commands for the ant-farm survey pipeline. Iron laws:

1. Run EXACTLY the command(s) in your prompt, from the repository root. Do not
   improvise flags, do not retry with variations, do not interpret results.
2. If the prompt includes a JSON payload, write it VERBATIM to the scratch file
   path given, then run the command with `--input <path>`.
3. Return `ok: true` and the command's raw stdout on success. On any failure,
   return `ok: false` and the complete stderr text. Never fabricate output.
4. You have no opinion about the survey. If a command's output looks wrong,
   return it anyway - the orchestrator decides.
```

`.claude/agents/surveyor.md`:

```markdown
---
name: surveyor
description: Frames a contested question before any farm runs - stasis, altitude, DISSOLVE check, reference class and base rate, Zwicky field, rival hypotheses including the null.
tools: Bash, Read, WebSearch, WebFetch
---

You frame contested questions for a survey instrument (Phase 1). Iron laws:

1. Check DISSOLVE first: if the question rests on a false presupposition or a
   fake binary, set dissolved=true, name the diagnosis, and emit a replacement
   question. A dissolved question needs nothing else.
2. Rival hypotheses: 2-4, always including the null ("no effect / no single
   answer"). Warm-start from prior basins when the brief carries them.
3. Every hypothesis text must be self-contained: no pronouns, no "the above",
   readable with zero context.

Protocol, in order:
- Stasis: is the dispute about fact, definition, quality, or policy?
- Altitude: what scale and horizon does an answer live at? One sentence.
- Reference class + base rate (outside view): "how often do theses shaped like
  this pay off?" State the class, then the rate, from search if available.
- Zwicky field: 2-4 dimensions x values spanning the possibility space; prune
  incoherent cells with a reason each.
- Rivals: the strongest 2-4 candidate positions, null included. Mark any that
  came from the warm-start brief as warm_started.

The warm-start brief in your prompt is prior corpus state: engage it, do not
re-derive it. Return only the structured output; it is data, not a message.
```

`.claude/agents/scout.md`:

```markdown
---
name: scout
description: Runs one round of one farm - sublate standing critiques, expand the hypothesis, compress state, emit atoms with warrants. Fresh context per round; continuity lives in the farm directory.
tools: Bash, Read, Grep, Glob, WebSearch, WebFetch
---

You run one round of one reasoning farm (Phase 2). Iron laws:

1. Read ONLY your own farm directory (the path in your prompt) and retrieve
   ONLY from the view collection. Never query the well; never read another
   farm's directory. Farms are evidence-blind to each other until stitch.
2. Every atom text must be self-contained: no pronouns, no "this shows",
   readable with zero context. Non-self-contained atoms are rejected.
3. Every supports edge carries a warrant - the rule licensing the inference,
   stated so it can be attacked.
4. When an edge targets existing material, quote the target's text EXACTLY as
   it appears; references resolve by exact text or corpus id.

Round protocol, in order. Before each pass, Read its pass file under
`.claude/skills/survey/references/` — expansion.md, compression.md,
sublation-and-decision.md. They carry the full protocol (meta-probes,
preservation gate, elevation test, evidence gates, worked examples); this
file is only the router.
- Sublate: read `critiques/*.json` in your farm dir. For each unaddressed
  finding: accept it (change your state), rebut it (emit a claim + rebuts
  edge), or qualify your thesis. Preservation gate: carry forward what the
  critique did NOT kill. Amputation check: excise what it did - no zombie
  claims. Record each disposition. Fill ledger_entry honestly:
  novel_content=false if your patch added nothing new. Two consecutive
  content-free patches force ELEVATE or CONCEDE - the gate checks.
- Expand: retrieval (view) + search on your persona's blind spots; pursue
  anomalies abductively; emit atoms and edges as you go.
- Compress: one compressed_state paragraph - your thesis, its strongest
  support, its live risks. Set confidence_r and confidence_c (ordinal bands).
- Decide: CONTINUE | CONCLUDE | ELEVATE | CONCEDE (with died_because).
  CONCLUDE needs a HIGH falsification trigger on record ("would a false
  thesis survive this test?"), no standing undercutters, a clean ledger.
  The script enforces this; do not claim CONCLUDE you cannot defend.

Inhabit your assigned persona's knowledge and priorities; keep its prose plain.
```

`.claude/agents/blind-critic.md`:

```markdown
---
name: blind-critic
description: Refutes one farm's reasoning presented as an authorless third-party document - warrant probes, premortem, severity grading, rebutting/undercutting classification.
tools: Bash, Read, WebSearch, WebFetch
---

You review a reasoning trace you did not write (Phase 3). Iron laws:

1. The trace is an authorless third-party document. Attack the reasoning as
   found; never address its author.
2. Read the trace file given in your prompt and retrieve from the WELL
   collection (contested and buried material included). Do not read other
   farms' directories.
3. Every finding's text must be self-contained and quote its target_text
   EXACTLY as written in the trace or corpus - resolution is by exact text.
4. Classify every finding: rebutting (the claim is false) or undercutting
   (the inference is unlicensed). Grade severity low/med/high - high means
   the thesis cannot stand if this holds.

Required probes — Read `.claude/skills/survey/references/critique-probes.md`
first; it carries the full probe protocol (meta-probes, fact-check-with-search,
severity calibration). This file is only the router.
- Warrant probe: attack the licence of the strongest supports-inference, not
  its grounds.
- Premortem: "It is 12 months from now and the thesis failed - write the
  history." Distill that history into ONE self-contained premortem sentence;
  it becomes a named risk the farm must answer or rebut.
- Contradiction sweep: statements in the trace that cannot both be true.
- Evidence challenge: evidence counted as support that is consistent with
  rival hypotheses too (non-diagnostic).

Report findings even when the trace is good; an empty findings list with a
serious premortem is a legitimate report. Never soften to be agreeable.
```

`.claude/agents/hole-finder.md`:

```markdown
---
name: hole-finder
description: Adversarially probes the corpus for absent considerations - produces a consideration the survey missed, or fails trying. Its failure streak is a coverage signal.
tools: Bash, Read, WebSearch, WebFetch
---

You probe a survey corpus for holes (Phase 6). Iron laws:

1. Your job is to produce ONE consideration genuinely ABSENT from the corpus -
   not a paraphrase, not a recombination of what is there.
2. The candidate must be self-contained and material: it would change how a
   reader weighs the hypotheses if true.
3. Failing honestly is a valid output (candidate=null). Your failures feed the
   coverage certificate; a fabricated near-duplicate corrupts it.

Method: read the declaration and view summary in your prompt; look where the
corpus is thin - empty Zwicky cells, unexamined stakeholders, absent time
horizons, missing failure modes, unpriced externalities. Search the open web
from an angle no farm took. Emit the single strongest candidate with your
reasoning, or null with what you tried.
```

`.claude/agents/stitcher.md`:

```markdown
---
name: stitcher
description: Cross-farm synthesis - ACH matrix over evidence x hypotheses, disagreement investigation, basin or crux-conditional frontier declaration. Never averages incompatible positions.
tools: Bash, Read
---

You stitch parallel farms into a map (Phase 5). Iron laws:

1. Score evidence AGAINST hypotheses (consistent | inconsistent | neutral).
   The winner is decided by LEAST INCONSISTENCY, never by confirmation count -
   the script computes it from your cells; score honestly and completely.
2. Investigate ONLY disagreements between farms. Where farms agree, move on.
3. Never average incompatible positions. Where one basin dominates, declare a
   basin. Where the answer is weighting-dependent, declare a frontier with
   crux conditions: "under W1, A; under W2, B; the crux is X."
4. DISSOLVE remains available: if stitching reveals the question itself is
   malformed, say so with a replacement question.
5. Quote evidence and hypothesis texts EXACTLY as given in your brief - cells
   resolve by exact text match; a paraphrased cell is discarded.

Your brief carries every farm's compressed state, the evidence inventory, and
the hypotheses. Atoms you emit during investigations follow the same rules as
scouts: self-contained text, warrants on supports edges.
```

`.claude/agents/sentinel.md`:

```markdown
---
name: sentinel
description: Run-opening tripwire check - tests each standing tripwire against the current state of the world via web search and reports which fired.
tools: Bash, Read, WebSearch, WebFetch
---

You check standing tripwires against the world (Phase 0). Iron laws:

1. A tripwire fires only on EVIDENCE, not on vibes. fired=true requires a
   dated, sourceable development satisfying the tripwire's condition.
2. Report every tripwire you were given, fired or not.
3. The evidence text must be self-contained (it becomes a corpus atom):
   include what happened, when, and the source.

For each tripwire in your prompt: search for developments since the corpus
last ran; judge strictly whether the stated condition is met; report
fired/not-fired with your evidence sentence either way.
```

`.claude/agents/curator.md`:

```markdown
---
name: curator
description: Renders the survey map as prose - basins, cruxes, ridges, holes - from the declaration and materialized view. Rendering only; admission to the view is computed, not curated.
tools: Bash, Read
---

You render the map (Phase 7). Iron laws:

1. You render; you never admit. The view was computed by a gate; work with
   what is in it. Do not promote, demote, or editorialize about atoms.
2. Preserve dissent. Contested nodes and standing challenges appear AS
   contested; a frontier declaration renders as a frontier, never averaged
   into a fake consensus.
3. Report R/E/C as ordinal bands, never as numbers or probabilities.

Produce MAP.md: the question; the declaration (basin or crux-conditional
frontier) in plain prose; the cruxes that decide between positions; conceded
hypotheses with their died-because records; standing tripwires (the map's
staleness sensors); and the holes the hole-finder exposed. Wikilink node ids
in [[double brackets]] so Obsidian resolves them to the rendered pages.
```

- [ ] **Step 4: Port the proven pass files from dialectic-plugin**

Source: the sibling repo's skill files at `../dialectic-plugin/skills/dialectic/` (same Projects directory as ant-farm). These are the prompt files proven in dialectic v1; spec §9.1 says this content is "kept and sharpened" — port and adapt, do not write fresh. If the sibling repo is missing, STOP and report BLOCKED; do not substitute from memory.

Create four files under `.claude/skills/survey/references/`, each roughly 2–3k tokens (spec §9.1's per-pass size), by adapting:

- `expansion.md` ← `EXPANSION.md` — keep the meta-probes, abductive anomaly pursuit, fact-grounding habits, and worked examples; adapt vocabulary: session/thesis → farm/hypothesis; retrieval is the VIEW collection only; markers become edges per `MARKERS.md` (`[BRIDGE: A→B]` → bridges edge, rebuttal markers → rebuts/undercuts edges, support with stated licence → supports edge + warrant).
- `compression.md` ← `COMPRESSION.md` — the compressed-state paragraph contract (thesis, strongest support, live risks) and confidence discipline; R/E/C stay ordinal bands, the composite is deleted (spec §9.1).
- `sublation-and-decision.md` ← `CRITIQUE.md` sections "Preservation Gate", "Elevation Test", "Evidence Gate for ELEVATE", and "Decision" — this is scout's sublate/decide protocol: disposition per critique (accept/rebut/qualify), carry forward what the critique did not kill, excise what it did, honest ledger entries, CONTINUE | CONCLUDE | ELEVATE | CONCEDE criteria.
- `critique-probes.md` ← `CRITIQUE.md` sections "Meta-Probes" and "Fact-Check with Web Search", plus severity grading and the rebutting-vs-undercutting distinction — blind-critic's protocol.

Strip from all four: stop-hook/session mechanics, HOLDOUT, output-format sections tied to v1 transcript scraping, and the contradictory R/E/C composite (all deleted by spec §9.1). Keep worked examples that translate; where one does not, note it under a closing `## Adaptation notes` heading rather than dropping it silently.

Style gate (spec §9.1): dispatch the `dialectic:prose-reviewer` agent over each ported file — one sentence = one executable instruction; imperative, positive, present; emphasis by position, not caps; one concrete example over three adjectives; one term per concept. Apply Critical/Important findings before committing. If the `dialectic:prose-reviewer` agent type is unavailable in this session, record that in the task report — do not skip silently.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_agents.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
uv run ruff check src tests
git add .claude/agents .claude/skills/survey/references tests/test_agents.py
git commit -m "feat: survey agent routers + pass references ported from proven dialectic v1 skills"
```

---

### Task 11: `workflows/survey.js` — the orchestrator

Phases 0–7 as deterministic JS over schema-forced agents and clerk-run CLI calls. The script never computes corpus logic — it dispatches, branches on CLI JSON, and enforces nothing the Python gates don't already enforce. `Date.now()`/`Math.random()` are unavailable in workflow scripts; all timestamps come from the CLI.

**Files:**
- Create: `workflows/survey.js`
- Create: `scripts/check_workflow.mjs` (syntax gate — see Step 2)
- Modify: `.github/workflows/ci.yml` (add syntax check)

**Interfaces:**
- Consumes: `args.question` (required), `args.schemas` (required — `export_schemas()` output), `args.mode` (`lean|default|saturate`, default `default`), `args.corpusDir` (default `corpus`), `args.personas`, `args.families` (defaults below), `args.stopAfter` (`sentinel`|`framing` — the spec's `--sentinel-only`/`--frame-only` standalone modes); agent types from Task 10; every CLI subcommand from Tasks 8–9
- Produces: a workflow returning `{run, question_id, farms, declaration, holes, view_size, transcripts, dissolved?}` — or an early `{dissolved: true, diagnosis, replacement_question}` from Phase 1

- [ ] **Step 1: Write the workflow script**

`workflows/survey.js`:

```javascript
export const meta = {
  name: 'survey',
  description: 'One ant-farm survey run: sentinel, framing, parallel farms with blind critique, verification floor, stitch, hole probing, materialize',
  phases: [
    { title: 'Setup', detail: 'bind question, allocate run id' },
    { title: 'Sentinel', detail: 'check standing tripwires (skipped on first run)' },
    { title: 'Framing', detail: 'surveyor: stasis, DISSOLVE, Zwicky field, rivals' },
    { title: 'Farms', detail: 'scout rounds with interleaved blind critique, gated decisions' },
    { title: 'Verify', detail: 'verification floor over novel atoms' },
    { title: 'Stitch', detail: 'ACH matrix, disagreement investigation, declaration' },
    { title: 'Holes', detail: 'hole-finder probes, optional gap wave' },
    { title: 'Materialize', detail: 'view, vault, keel exports, curator map, persona-swap' },
  ],
}

if (!args || !args.question) throw new Error('args.question is required')
if (!args.schemas || !args.schemas.scout_round) {
  throw new Error('args.schemas is required - run `uv run python -m antfarm schemas` ' +
    'and pass the parsed JSON (see .claude/skills/survey/SKILL.md)')
}

const S = args.schemas
const CORPUS = args.corpusDir || 'corpus'
const MODES = {
  lean: { farms: 1, maxRounds: 2, holeAttempts: 1, verifyCap: 4, gapWave: false },
  default: { farms: 3, maxRounds: 3, holeAttempts: 3, verifyCap: 12, gapWave: false },
  saturate: { farms: 3, maxRounds: 3, holeAttempts: 5, verifyCap: 24, gapWave: true },
}
const MODE = MODES[args.mode || 'default']
if (!MODE) throw new Error(`unknown mode: ${args.mode} (lean | default | saturate)`)
const PERSONAS = args.personas || [
  'a municipal procurement officer', 'a startup CFO', 'a graduate research assistant',
]
const FAMILIES = args.families || ['opus', 'sonnet', 'haiku']

// --- clerk bridge: the only way this script touches the corpus ---------------

const CLERK_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['ok', 'stdout', 'error'],
  properties: {
    ok: { type: 'boolean' },
    stdout: { type: 'string' },
    error: { type: ['string', 'null'] },
  },
}

async function cli(cmd, payload, label, phaseName) {
  const scratch = `/tmp/antfarm-${label.replace(/[^a-zA-Z0-9]+/g, '-')}.json`
  const steps = ['Execute this for the ant-farm survey pipeline, from the repository root.']
  if (payload !== undefined) {
    steps.push(
      `1. Write this JSON verbatim to ${scratch}:`,
      JSON.stringify(payload),
      `2. Run: uv run python -m antfarm ${cmd} --corpus ${CORPUS} --input ${scratch}`)
  } else {
    steps.push(`Run: uv run python -m antfarm ${cmd} --corpus ${CORPUS}`)
  }
  const r = await agent(steps.join('\n'), {
    agentType: 'clerk', label: `clerk:${label}`, phase: phaseName,
    effort: 'low', schema: CLERK_SCHEMA,
  })
  if (!r || !r.ok) {
    throw new Error(`antfarm ${cmd.split(' ')[0]} failed: ${r ? r.error : 'clerk returned nothing'}`)
  }
  return JSON.parse(r.stdout)
}

const q = (s) => JSON.stringify(s)  // shell-safe quoting for string flags

// --- prompts ------------------------------------------------------------------

const RETRIEVAL_NOTE = (collection) =>
  `Retrieval: from the repository root run\n` +
  `  uv run python -m antfarm query --corpus ${CORPUS} --collection ${collection} --text "..."\n` +
  `(returns [] before the first materialize).`

function sentinelPrompt(tripwires) {
  return [
    'Standing tripwires to check against the current state of the world.',
    'For each, search for developments and judge strictly whether its condition is met.',
    JSON.stringify(tripwires, null, 2),
  ].join('\n\n')
}

function surveyorPrompt(brief, sentinelNote) {
  return [
    `Frame this contested question for a survey: ${args.question}`,
    `Sentinel report: ${sentinelNote}`,
    `Warm-start brief (prior corpus state - engage it, do not re-derive it):`,
    JSON.stringify(brief, null, 2),
    RETRIEVAL_NOTE('view'),
  ].join('\n\n')
}

function scoutPrompt(farm, round, gateReasons) {
  return [
    `Farm ${farm.key}, round ${round} of ${MODE.maxRounds}.`,
    `Question: ${args.question}`,
    `Your hypothesis: ${farm.hypothesis_text}`,
    `Your persona: ${farm.persona}`,
    `Your farm directory: ${CORPUS}/farms/${RUN}/${farm.key}`,
    `Read turns.jsonl there for your prior rounds and critiques/*.json for the` +
    ` critic reports you must sublate. Read ONLY this farm's directory.`,
    gateReasons.length
      ? `Last round the gate blocked your decision. Reasons:\n- ${gateReasons.join('\n- ')}`
      : '',
    RETRIEVAL_NOTE('view'),
  ].filter(Boolean).join('\n\n')
}

function criticPrompt(farm, round) {
  return [
    `A third-party reasoning document on the question: ${args.question}`,
    `The document: ${CORPUS}/farms/${RUN}/${farm.key}/turns.jsonl (read it fully).`,
    `Critique round ${round}. Quote target_text exactly as written in the document.`,
    RETRIEVAL_NOTE('well'),
  ].join('\n\n')
}

function verifyPrompt(item) {
  return [
    `Independently verify this ${item.type} using sources OUTSIDE the survey corpus`,
    `(web search, primary documents). Confirm or refute; do not soften.`,
    `Text: ${item.text}`,
    `Return verified=true only with concrete corroborating evidence and a source.`,
  ].join('\n')
}

function stitcherPrompt(brief) {
  return [
    `Stitch these farms into a map for the question: ${args.question}`,
    `Score every evidence item against every hypothesis (quote texts exactly).`,
    `Investigate only disagreements between farms.`,
    JSON.stringify(brief, null, 2),
  ].join('\n\n')
}

function holePrompt(declaration, attempt) {
  return [
    `Attempt ${attempt + 1}: produce ONE consideration absent from this corpus,`,
    `or fail honestly (candidate=null). Question: ${args.question}`,
    `Current declaration: ${JSON.stringify(declaration)}`,
    RETRIEVAL_NOTE('view'),
    `The map pages live in ${CORPUS}/vault/ if it exists.`,
  ].join('\n\n')
}

function curatorPrompt(declaration, summary) {
  return [
    `Render MAP.md for the question: ${args.question}`,
    `Declaration: ${JSON.stringify(declaration, null, 2)}`,
    `Materialize summary: ${JSON.stringify(summary)}`,
    `Rendered node pages are in ${CORPUS}/vault/ - read a few for wikilink targets.`,
  ].join('\n\n')
}

function swapPrompt(pkg, persona) {
  return [
    `Persona-swap counterfactual. Below are the opening turns of a reasoning farm.`,
    `Regenerate the REMAINING iterations (${pkg.regen_iterations.join(', ')}) as if a`,
    ` different persona - ${persona} - had taken over from iteration ${pkg.start_iteration}.`,
    `Stay on the same question and hypothesis; change the vantage, not the topic.`,
    `Emit expand and compress turns (and sublate where you address prior critique)`,
    ` for each regenerated iteration.`,
    `Context turns:`,
    JSON.stringify(pkg.context, null, 2),
  ].join('\n')
}

// --- Phase: Setup ---------------------------------------------------------------

phase('Setup')
const setup = await cli(`run-new --question ${q(args.question)}`, undefined, 'run-new', 'Setup')
const RUN = setup.run
log(`run ${RUN} on question ${setup.question_id} (first_run=${setup.first_run}, mode=${args.mode || 'default'})`)

// --- Phase 0: Sentinel ------------------------------------------------------------

phase('Sentinel')
let sentinelNote = 'No standing tripwires were checked this run.'
if (!setup.first_run) {
  const tripwires = await cli('tripwires-list', undefined, 'tripwires-list', 'Sentinel')
  if (tripwires.length) {
    const report = await agent(sentinelPrompt(tripwires), {
      agentType: 'sentinel', label: 'sentinel', phase: 'Sentinel',
      schema: S.sentinel_report,
    })
    const fired = report ? report.checks.filter((c) => c.fired) : []
    for (const check of fired) {
      const res = await cli(`tripwire-fire --run ${RUN} --id ${check.tripwire_id}`,
        { evidence: check.evidence }, `fire-${check.tripwire_id}`, 'Sentinel')
      log(`tripwire ${check.tripwire_id} fired; ${res.affected.length} node(s) contested`)
    }
    sentinelNote = fired.length
      ? `${fired.length} tripwire(s) fired this run: ` +
        fired.map((c) => c.evidence).join(' | ')
      : `${tripwires.length} tripwire(s) checked; none fired.`
  }
}
if (args.stopAfter === 'sentinel') {  // spec §5: --sentinel-only
  return { run: RUN, question_id: setup.question_id, sentinel: sentinelNote }
}

// --- Phase 1: Framing --------------------------------------------------------------

phase('Framing')
const warmBrief = await cli('brief', undefined, 'brief', 'Framing')
const framing = await agent(surveyorPrompt(warmBrief, sentinelNote), {
  agentType: 'surveyor', label: 'surveyor', phase: 'Framing', schema: S.framing,
})
if (!framing) throw new Error('surveyor agent failed')
const framed = await cli(`harvest-framing --run ${RUN}`, framing, 'harvest-framing', 'Framing')
if (framing.dissolve.dissolved) {
  log(`DISSOLVE at framing: ${framing.dissolve.diagnosis}`)
  return {
    dissolved: true, at: 'framing', run: RUN,
    diagnosis: framing.dissolve.diagnosis,
    replacement_question: framing.dissolve.replacement_question,
  }
}
if (args.stopAfter === 'framing') {  // spec §5: --frame-only
  return { run: RUN, question_id: setup.question_id, sentinel: sentinelNote,
           rivals: framed.rivals }
}
const farms = framed.rivals.slice(0, MODE.farms).map((rival, i) => ({
  key: String.fromCharCode(65 + i),
  hypothesis_id: rival.id,
  hypothesis_text: rival.text,
  persona: PERSONAS[i % PERSONAS.length],
  family: FAMILIES[i % FAMILIES.length],
}))
for (const farm of farms) {
  await cli(
    `farm-init --run ${RUN} --farm ${farm.key} --hypothesis-id ${farm.hypothesis_id}` +
    ` --hypothesis-text ${q(farm.hypothesis_text)} --persona ${q(farm.persona)}` +
    ` --family ${farm.family}`,
    undefined, `farm-init-${farm.key}`, 'Framing')
}
log(`${farms.length} farm(s): ` +
  farms.map((f) => `${f.key}=${f.family}/${f.persona}`).join(', '))

// --- Phases 2+3: Farms (scout rounds interleaved with blind critique) -------------

phase('Farms')
async function runFarm(farm) {
  let gateReasons = []
  for (let round = 1; round <= MODE.maxRounds; round++) {
    const out = await agent(scoutPrompt(farm, round, gateReasons), {
      agentType: 'scout', model: farm.family,
      label: `scout:${farm.key}:r${round}`, phase: 'Farms', schema: S.scout_round,
    })
    if (!out) {
      await cli(`farm-outcome --run ${RUN} --farm ${farm.key} --decision ELEVATE`,
        undefined, `outcome-${farm.key}`, 'Farms')
      return { farm: farm.key, decision: 'ELEVATE', reasons: ['scout agent failed'] }
    }
    const harvested = await cli(
      `harvest-scout --run ${RUN} --farm ${farm.key} --round ${round}` +
      ` --family ${farm.family} --persona ${q(farm.persona)}`,
      out, `harvest-${farm.key}-r${round}`, 'Farms')
    if (harvested.rejected.length || harvested.unresolved.length) {
      log(`farm ${farm.key} r${round}: ${harvested.rejected.length} atom(s) rejected, ` +
        `${harvested.unresolved.length} edge(s) unresolved`)
    }
    const finalRound = round === MODE.maxRounds
    const gate = await cli(
      `gate --run ${RUN} --farm ${farm.key}${finalRound ? ' --final-round' : ''}`,
      out, `gate-${farm.key}-r${round}`, 'Farms')
    if (gate.decision !== 'CONTINUE') {
      await cli(
        `farm-outcome --run ${RUN} --farm ${farm.key} --decision ${gate.decision}` +
        (out.died_because ? ` --died-because ${q(out.died_because)}` : ''),
        undefined, `outcome-${farm.key}`, 'Farms')
      return { farm: farm.key, decision: gate.decision, forced: gate.forced,
               reasons: gate.reasons }
    }
    gateReasons = gate.reasons
    const critique = await agent(criticPrompt(farm, round), {
      agentType: 'blind-critic', label: `critic:${farm.key}:r${round}`,
      phase: 'Farms', schema: S.critique_report,
    })
    if (critique) {
      await cli(
        `harvest-critique --run ${RUN} --farm ${farm.key} --round ${round}`,
        critique, `critique-${farm.key}-r${round}`, 'Farms')
    }
  }
  // unreachable: the gate never returns CONTINUE on the final round
  return { farm: farm.key, decision: 'ELEVATE', reasons: ['loop exhausted'] }
}

const outcomes = (await parallel(farms.map((farm) => () => runFarm(farm)))).filter(Boolean)
log('farm outcomes: ' + outcomes.map((o) => `${o.farm}=${o.decision}`).join(', '))

// --- Phase 4: Verification floor ---------------------------------------------------

phase('Verify')
const queue = await cli('verification-queue', undefined, 'verification-queue', 'Verify')
const toVerify = queue.slice(0, MODE.verifyCap)
if (queue.length > toVerify.length) {
  log(`verification capped at ${MODE.verifyCap} of ${queue.length} queued atoms`)
}
const verifications = (await parallel(toVerify.map((item) => () =>
  agent(verifyPrompt(item), {
    label: `verify:${item.id}`, phase: 'Verify', schema: S.verification_result,
  }).then((v) => v && { atom_id: item.id, verified: v.verified,
                        evidence: v.evidence, source: v.source })
))).filter(Boolean)
if (verifications.length) {
  const verified = await cli(`harvest-verify --run ${RUN}`, verifications,
    'harvest-verify', 'Verify')
  log(`verification floor: ${verified.verified.length}/${verifications.length} upgraded`)
}

// --- Phase 5: Stitch ----------------------------------------------------------------

phase('Stitch')
let declaration = null
let dissolvedAtStitch = null
async function runStitch(label) {
  const brief = await cli(`stitch-brief --run ${RUN}`, undefined, `stitch-brief-${label}`, 'Stitch')
  const stitch = await agent(stitcherPrompt(brief), {
    agentType: 'stitcher', label: `stitcher-${label}`, phase: 'Stitch', schema: S.stitch,
  })
  if (!stitch) return
  const res = await cli(`harvest-stitch --run ${RUN}`, stitch, `harvest-stitch-${label}`, 'Stitch')
  declaration = res.declaration
  if (stitch.dissolve.dissolved) {
    dissolvedAtStitch = {
      diagnosis: stitch.dissolve.diagnosis,
      replacement_question: stitch.dissolve.replacement_question,
    }
  }
}
await runStitch('1')

// --- Phase 6: Holes and the gap-directed spawn decision -----------------------------

phase('Holes')
const holes = []
let failureStreak = 0
for (let attempt = 0; attempt < MODE.holeAttempts; attempt++) {
  const hf = await agent(holePrompt(declaration, attempt), {
    agentType: 'hole-finder', label: `hole-finder:${attempt + 1}`,
    phase: 'Holes', schema: S.hole_finder,
  })
  if (!hf || !hf.candidate) { failureStreak++; continue }
  const probed = await cli('probe', { text: hf.candidate }, `probe-${attempt + 1}`, 'Holes')
  if (probed.novel) { holes.push(hf.candidate); failureStreak = 0 } else { failureStreak++ }
}
log(`hole-finder: ${holes.length} hit(s), closing failure streak ${failureStreak}`)
if (holes.length) {
  const holeAtoms = await cli(
    `harvest-atoms --run ${RUN} --farm hole-finder --persona hole-finder`,
    { atoms: holes.map((text) => ({ type: 'claim', text })), edges: [] },
    'harvest-holes', 'Holes')
  if (MODE.gapWave && (!budget.total || budget.remaining() > 100_000)) {
    const gapFarms = holes.slice(0, 2).map((text, i) => ({
      key: `G${i + 1}`,
      hypothesis_id: holeAtoms.atom_ids[i],
      hypothesis_text: text,
      persona: PERSONAS[(farms.length + i) % PERSONAS.length],
      family: FAMILIES[(farms.length + i) % FAMILIES.length],
    }))
    for (const farm of gapFarms) {
      await cli(
        `farm-init --run ${RUN} --farm ${farm.key} --hypothesis-id ${farm.hypothesis_id}` +
        ` --hypothesis-text ${q(farm.hypothesis_text)} --persona ${q(farm.persona)}` +
        ` --family ${farm.family}`,
        undefined, `farm-init-${farm.key}`, 'Holes')
    }
    log(`gap wave: spawning ${gapFarms.length} farm(s) briefed at the largest holes`)
    const gapOutcomes = (await parallel(gapFarms.map((farm) => () => runFarm(farm))))
      .filter(Boolean)
    outcomes.push(...gapOutcomes)
    await runStitch('2')
  }
}

// --- Phase 7: Materialize ------------------------------------------------------------

phase('Materialize')
const summary = await cli(`materialize --run ${RUN}`, undefined, 'materialize', 'Materialize')
log(`view=${summary.view_size} pages=${summary.pages} ` +
  `tripwires+${summary.tripwires_registered} farms=${summary.farms_exported.join(',')}`)

const curated = await agent(curatorPrompt(declaration, summary), {
  agentType: 'curator', label: 'curator', phase: 'Materialize', schema: S.curator,
})
if (curated) await cli('map-write', curated, 'map-write', 'Materialize')

// persona-swap counterfactual over the first farm that ran multiple iterations
const swapFarm = farms[0]
if (swapFarm) {
  const pkg = await cli(
    `persona-swap-prepare --run ${RUN} --farm ${swapFarm.key} --start-iteration 2`,
    undefined, 'persona-swap-prepare', 'Materialize')
  if (pkg.eligible) {
    const altPersona = PERSONAS.find((p) => p !== swapFarm.persona) || 'a careful auditor'
    const regen = await agent(swapPrompt(pkg, altPersona), {
      label: 'persona-swap', phase: 'Materialize', schema: S.persona_swap,
    })
    if (regen) {
      await cli(
        `persona-swap-write --run ${RUN} --farm ${swapFarm.key} --start-iteration 2`,
        regen, 'persona-swap-write', 'Materialize')
      log(`persona-swap counterfactual written for farm ${swapFarm.key}`)
    }
  }
}

return {
  run: RUN,
  question_id: setup.question_id,
  farms: outcomes,
  declaration,
  holes,
  view_size: summary.view_size,
  transcripts: summary.farms_exported,
  ...(dissolvedAtStitch ? { dissolved: true, at: 'stitch', ...dissolvedAtStitch } : {}),
}
```

- [ ] **Step 2: Write the syntax gate and run it**

Workflow scripts use top-level `return`/`await` because the runtime executes the body inside an async function — so plain `node --check` (module grammar, where top-level `return` is a SyntaxError) cannot validate them. Parse it the way the runtime does:

`scripts/check_workflow.mjs`:

```javascript
// Parses workflows/survey.js the way the Workflow runtime does: body of an
// async function with the runtime globals in scope. Top-level return/await
// are legal there; plain `node --check` would reject them.
import { readFileSync } from 'node:fs'

const src = readFileSync('workflows/survey.js', 'utf8').replace(/^export\s+/m, '')
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
new AsyncFunction('args', 'agent', 'parallel', 'pipeline', 'phase', 'log',
  'budget', 'workflow', src)
console.log('workflow syntax ok')
```

Run: `node scripts/check_workflow.mjs`
Expected: `workflow syntax ok` (a SyntaxError anywhere in survey.js throws with a line reference).

- [ ] **Step 3: Add the CI syntax gate**

In `.github/workflows/ci.yml`, after the `Type check` step, add:

```yaml
      - name: Workflow script syntax
        run: node scripts/check_workflow.mjs
```

- [ ] **Step 4: Commit**

```bash
uv run ruff check src tests
git add workflows/survey.js scripts/check_workflow.mjs .github/workflows/ci.yml
git commit -m "feat: survey.js orchestrator - phases 0-7 over schema-forced agents"
```

---

### Task 12: Invocation skill, pipeline smoke test, CI, README

The workflow needs `args.schemas` generated at invocation time — a project skill documents the two-step launch so any session does it right. The pipeline smoke script drives the full Python side exactly as survey.js does (fixture agent outputs through CLI subprocesses), offline.

**Files:**
- Create: `.claude/skills/survey/SKILL.md`
- Create: `scripts/smoke_pipeline.py`
- Modify: `.github/workflows/ci.yml` (add smoke step)
- Modify: `README.md` (status section)

**Interfaces:**
- Consumes: every CLI subcommand; the fixtures pattern from `tests/helpers.py` (inlined — scripts don't import from tests/)
- Produces: `/survey` skill; `scripts/smoke_pipeline.py` exiting non-zero on first failed check; CI gate

- [ ] **Step 1: Write the skill**

`.claude/skills/survey/SKILL.md`:

```markdown
---
name: survey
description: Run an ant-farm survey on a contested question via the dynamic workflow. Use when the user asks to survey a question, run ant-farm, or map an argument space.
---

# Run a survey

Requirements: Claude Code >= 2.1.154 with workflows enabled, `uv` installed,
repo dependencies synced (`uv sync`).

1. Generate the agent output schemas (they are pydantic-derived; never
   hand-write them):

   ```bash
   uv run python -m antfarm schemas
   ```

2. Invoke the Workflow tool with the parsed JSON:

   - `scriptPath`: `workflows/survey.js`
   - `args`:
     - `question` (required): the contested question, verbatim.
     - `schemas` (required): the parsed JSON object from step 1.
     - `mode`: `lean` | `default` | `saturate` (default `default`; see spec §11).
     - `corpusDir`: corpus directory (default `corpus`). One corpus per
       question - reuse the same dir to accumulate across runs (spec §8).
     - `personas` / `families`: optional overrides (mundane personas beat
       exotic ones; families rotate over opus/sonnet/haiku).
     - `stopAfter`: `sentinel` or `framing` to run phases 0-1 standalone
       (the spec's --sentinel-only / --frame-only modes).

3. On a DISSOLVE result, relay the diagnosis and replacement question to the
   user; re-run only if they adopt the replacement.

4. After the run: the map is `corpus/vault/MAP.md`, node pages sit beside it,
   keel exports are under `corpus/exports/<run>/`, and re-running the same
   question warm-starts from the accumulated corpus.
```

- [ ] **Step 2: Write the pipeline smoke script**

`scripts/smoke_pipeline.py`:

```python
"""End-to-end smoke test for the survey pipeline's Python side.

Drives the CLI exactly as workflows/survey.js does - fixture agent outputs in,
JSON out - through: run-new -> framing -> two farms (one CONCLUDE, one CONCEDE)
with critique and gates -> verification floor -> stitch -> probe -> materialize.
Offline: ANTFARM_EMBED=hash, no model downloads.

Run: uv run python scripts/smoke_pipeline.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKS: list[str] = []


def check(name: str, condition: bool) -> None:
    print(f"  [{'ok' if condition else 'FAIL'}] {name}")
    CHECKS.append(name)
    if not condition:
        sys.exit(f"pipeline smoke failed at: {name}")


def cli(corpus: Path, *argv: str, payload=None):
    cmd = [sys.executable, "-m", "antfarm", *argv, "--corpus", str(corpus)]
    kwargs = {}
    if payload is not None:
        cmd += ["--input", "-"]
        kwargs["input"] = json.dumps(payload)
    env = {**os.environ, "ANTFARM_EMBED": "hash"}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, **kwargs)
    if proc.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{proc.stderr}")
    return json.loads(proc.stdout)


QUESTION = "Is rooftop solar a good investment for US homeowners?"
HYP_A = "Rooftop solar pays back within ten years in most US states."
HYP_B = "Rooftop solar only pays back where net metering survives."
NULL = "Rooftop solar payback is too variable for any general claim."
CLAIM_A = "Residential solar payback periods fell below ten years in over thirty states."
EVIDENCE_A = "Lawrence Berkeley National Laboratory tracked 2024 paybacks averaging nine years."
CRITIQUE_A = "Payback estimates ignore inverter replacement costs at year twelve."
PREMORTEM_A = "The payback thesis failed because net metering rollbacks spread beyond California."
REBUT_1 = "Inverter replacement adds under one year to average payback in current models."
REBUT_2 = "Net metering rollback proposals stalled in most state legislatures through 2026."
TRIGGER_A = "Three additional states adopting California-style net billing by 2027 falsifies the payback thesis."

FRAMING = {
    "stasis": "quality", "altitude": "US household level, 10-year horizon",
    "dissolve": {"dissolved": False, "diagnosis": None, "replacement_question": None},
    "reference_class": "household capital-improvement investments",
    "base_rate": "most such investments recoup within their advertised window",
    "zwicky_dimensions": [{"name": "policy", "values": ["net metering", "net billing"]},
                          {"name": "region", "values": ["sunbelt", "northern"]}],
    "incoherent_cells": [],
    "rivals": [{"text": HYP_A, "is_null": False, "warm_started": False},
               {"text": HYP_B, "is_null": False, "warm_started": False},
               {"text": NULL, "is_null": True, "warm_started": False}],
}


def scout_a(round_n: int, decision: str) -> dict:
    base = {
        "sublation": [], "expansion": f"Round {round_n}: payback analysis.",
        "atoms": [{"type": "claim", "text": CLAIM_A, "strength": None,
                   "diagnosticity": None},
                  {"type": "evidence", "text": EVIDENCE_A, "strength": 4,
                   "diagnosticity": "high"}],
        "edges": [{"src": EVIDENCE_A, "dst": CLAIM_A, "rel": "supports",
                   "warrant": "measured paybacks license the general claim"}],
        "falsification_triggers": [],
        "compressed_state": f"Thesis after round {round_n}: sub-decade payback holds.",
        "confidence_r": "med", "confidence_c": "med",
        "ledger_entry": None, "decision": decision, "died_because": None,
    }
    if round_n >= 2:
        base["sublation"] = [
            {"critique": CRITIQUE_A, "disposition": "rebutted", "response": REBUT_1},
            {"critique": PREMORTEM_A, "disposition": "rebutted", "response": REBUT_2}]
        base["atoms"] = [{"type": "claim", "text": REBUT_1, "strength": None,
                          "diagnosticity": None},
                         {"type": "claim", "text": REBUT_2, "strength": None,
                          "diagnosticity": None}]
        base["edges"] = [{"src": REBUT_1, "dst": CRITIQUE_A, "rel": "rebuts",
                          "warrant": None},
                         {"src": REBUT_2, "dst": PREMORTEM_A, "rel": "rebuts",
                          "warrant": None}]
        base["falsification_triggers"] = [{"text": TRIGGER_A, "severity": "high"}]
        base["ledger_entry"] = {"trigger": "round 1 critique",
                                "change": "rebutted cost and policy challenges",
                                "novel_content": True}
    return base


CRITIQUE = {
    "findings": [{"target_text": CLAIM_A, "kind": "warrant_probe",
                  "classification": "undercutting", "severity": "high",
                  "text": CRITIQUE_A}],
    "premortem": PREMORTEM_A,
    "summary": "Cost omission probe plus policy premortem.",
}

SCOUT_B = {
    "sublation": [], "expansion": "Round 1: policy-dependence analysis.",
    "atoms": [{"type": "claim",
               "text": "Net billing states show payback periods beyond fifteen years.",
               "strength": None, "diagnosticity": None}],
    "edges": [], "falsification_triggers": [],
    "compressed_state": "Thesis: policy dependence dominates, but the general "
                        "payback claim explains the same evidence.",
    "confidence_r": "low", "confidence_c": "med",
    "ledger_entry": None, "decision": "CONCEDE",
    "died_because": "the general payback thesis explains the evidence more simply",
}

STITCH = {
    "ach": [{"evidence_text": EVIDENCE_A, "hypothesis_text": HYP_A,
             "consistency": "consistent"},
            {"evidence_text": EVIDENCE_A, "hypothesis_text": NULL,
             "consistency": "inconsistent"}],
    "investigations": [],
    "declaration_kind": "basin",
    "declaration_summary": "The sub-decade payback basin dominates; policy is the crux.",
    "positions": [{"hypothesis_text": HYP_A, "condition": None}],
    "dissolve": {"dissolved": False, "diagnosis": None, "replacement_question": None},
}

SWAP = {"turns": [
    {"phase": "expand", "iteration": 2, "content": "As an auditor: check the cost model."},
    {"phase": "compress", "iteration": 2, "content": "Audited thesis: payback holds."}]}


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        corpus = Path(tmp) / "corpus"

        print("setup + framing")
        setup = cli(corpus, "run-new", "--question", QUESTION)
        run = setup["run"]
        check("first run allocated r0001", run == "r0001" and setup["first_run"])
        check("schemas export includes every agent output",
              "scout_round" in cli(corpus, "schemas"))
        framed = cli(corpus, "harvest-framing", "--run", run, payload=FRAMING)
        check("three rivals harvested incl. null", len(framed["rivals"]) == 3)
        for farm, rival in (("A", framed["rivals"][0]), ("B", framed["rivals"][1])):
            cli(corpus, "farm-init", "--run", run, "--farm", farm,
                "--hypothesis-id", rival["id"], "--hypothesis-text", rival["text"],
                "--persona", "an energy analyst", "--family", "opus")

        print("farm A: continue -> critique -> sublate -> conclude")
        r1 = scout_a(1, "CONTINUE")
        cli(corpus, "harvest-scout", "--run", run, "--farm", "A", "--round", "1",
            "--family", "opus", "--persona", "analyst", payload=r1)
        gate1 = cli(corpus, "gate", "--run", run, "--farm", "A", payload=r1)
        check("round 1 gate says CONTINUE", gate1["decision"] == "CONTINUE")
        cli(corpus, "harvest-critique", "--run", run, "--farm", "A", "--round", "1",
            payload=CRITIQUE)
        blocked = cli(corpus, "gate", "--run", run, "--farm", "A",
                      payload=scout_a(1, "CONCLUDE"))
        check("premature CONCLUDE is blocked", blocked["decision"] == "CONTINUE"
              and blocked["forced"])
        r2 = scout_a(2, "CONCLUDE")
        cli(corpus, "harvest-scout", "--run", run, "--farm", "A", "--round", "2",
            "--family", "opus", "--persona", "analyst", payload=r2)
        gate2 = cli(corpus, "gate", "--run", run, "--farm", "A", payload=r2)
        check("sublated CONCLUDE passes the gate", gate2["decision"] == "CONCLUDE")
        cli(corpus, "farm-outcome", "--run", run, "--farm", "A",
            "--decision", "CONCLUDE")

        print("farm B: honest concession")
        cli(corpus, "harvest-scout", "--run", run, "--farm", "B", "--round", "1",
            "--family", "sonnet", "--persona", "analyst", payload=SCOUT_B)
        gate_b = cli(corpus, "gate", "--run", run, "--farm", "B", payload=SCOUT_B)
        check("CONCEDE passes through the gate", gate_b["decision"] == "CONCEDE")
        cli(corpus, "farm-outcome", "--run", run, "--farm", "B", "--decision",
            "CONCEDE", "--died-because", SCOUT_B["died_because"])

        print("verification floor + stitch")
        queue = cli(corpus, "verification-queue")
        check("verification queue is populated", len(queue) >= 2)
        cli(corpus, "harvest-verify", "--run", run, payload=[
            {"atom_id": item["id"], "verified": True,
             "evidence": "independently corroborated", "source": "example.org"}
            for item in queue])
        stitched = cli(corpus, "harvest-stitch", "--run", run, payload=STITCH)
        check("declaration computed with ACH winner and E band",
              stitched["declaration"]["kind"] == "basin"
              and stitched["declaration"]["ach"]["winner"] is not None
              and stitched["declaration"]["e_band"] in ("low", "med", "high"))

        print("holes + materialize + counterfactual")
        dup = cli(corpus, "probe", payload={"text": HYP_A})
        novel = cli(corpus, "probe",
                    payload={"text": "zqx wvj kkp qqe zzt xxr wwy vvu"})
        check("probe separates duplicate from novel",
              dup["novel"] is False and novel["novel"] is True)
        summary = cli(corpus, "materialize", "--run", run)
        check("view materialized with pages", summary["view_size"] >= 1
              and summary["pages"] == summary["view_size"])
        check("HIGH trigger registered as tripwire",
              summary["tripwires_registered"] >= 1
              and len(cli(corpus, "tripwires-list")) >= 1)
        stats_b = json.loads(
            (corpus / "exports" / run / "B" / "stats.json").read_text())
        check("CONCEDE exports as conceded, never degraded",
              stats_b["coherence_label"] == "conceded")
        trace_a = corpus / "exports" / run / "A" / "trace.jsonl"
        lines = [json.loads(line) for line in trace_a.read_text().splitlines()]
        check("keel trace lines carry exactly the five schema keys",
              all(set(line) == {"turn", "role", "phase", "iteration", "content"}
                  for line in lines))
        brief = cli(corpus, "brief")
        check("warm brief carries the conceded hypothesis",
              any(c["text"] == HYP_B for c in brief["conceded"]))
        pkg = cli(corpus, "persona-swap-prepare", "--run", run, "--farm", "A",
                  "--start-iteration", "2")
        check("persona-swap package is eligible", pkg["eligible"] is True)
        swapped = cli(corpus, "persona-swap-write", "--run", run, "--farm", "A",
                      "--start-iteration", "2", payload=SWAP)
        check("persona-swap counterfactual written", swapped["turns"] >= 4)

        second = cli(corpus, "run-new", "--question", QUESTION)
        check("second run resumes the corpus", second["run"] == "r0002"
              and second["first_run"] is False)

    print(f"\npipeline smoke passed: {len(CHECKS)} checks")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the smoke script**

Run: `uv run python scripts/smoke_pipeline.py`
Expected: `pipeline smoke passed: 18 checks`

- [ ] **Step 4: Add the CI step and update the README**

In `.github/workflows/ci.yml`, after the existing `Smoke test (end-to-end pipeline)` step, add:

```yaml
      - name: Pipeline smoke test (survey CLI, offline embeddings)
        run: uv run python scripts/smoke_pipeline.py
```

In `README.md`, replace the `## Status` section body with:

```markdown
Corpus core (plan 1) and the survey pipeline (plan 2) are implemented: the
`antfarm` Python package (schemas, reducer, stores, graph queries, transcripts),
the `python -m antfarm` CLI, the seven survey agents, and the
`workflows/survey.js` orchestrator. Run a survey via the `/survey` skill
(requires Claude Code >= 2.1.154 with dynamic workflows). The coverage
certificate (plan 3) and the dialectic-plugin v2 consumer seam (plan 4) are
next. The full design lives in
[`docs/specs/2026-07-03-ant-farm-design.md`](docs/specs/2026-07-03-ant-farm-design.md).
```

- [ ] **Step 5: Full gate and commit**

Run: `uv run pytest -v && uv run pytest -m eval -v && uv run ruff check src tests && uv run mypy src && uv run python scripts/smoke.py && uv run python scripts/smoke_pipeline.py && node scripts/check_workflow.mjs`
Expected: everything green

```bash
git add .claude/skills/survey/SKILL.md scripts/smoke_pipeline.py .github/workflows/ci.yml README.md
git commit -m "feat: survey skill, offline pipeline smoke test, CI gates"
```

---

## Live-fire validation (post-merge, manual)

The workflow itself cannot run in CI (it needs the Claude Code runtime and spends real tokens). After merge, validate once by hand:

1. `uv sync && uv run python -m antfarm schemas` — capture the JSON.
2. Invoke the `/survey` skill on a cheap question with `mode: "lean"` (1 farm, 2 rounds).
3. Confirm: `corpus/vault/MAP.md` exists, `corpus/exports/r0001/A/{trace.jsonl,stats.json}` parse, `/workflows` showed all eight phases, and a second lean run warm-starts (`first_run=false`, sentinel checks the registered tripwires).

File follow-up issues for prompt-quality problems (agent prose, not plumbing) rather than blocking the merge on them.

## Deferred to later plans

- **Plan 3 (coverage certificate):** Good-Turing/Chao1 estimators over `entailment_clusters`, rarefaction curve resuming across runs, correlation discount / n_eff from cluster co-membership (spec §6), Zwicky named-gap grid recall (framing.json already persists the field), hole-finder survival-streak line item (survey.js already logs streaks), the E band's rarefaction-slope component, certificate calibration eval (spec §10.2), vantage-level yield stats ("the instrument learns its optics", spec §8), and Phase 6 spawning driven by the certificate instead of hole hits alone.
- **Plan 4 (dialectic-plugin v2):** the deletions and consumer changes in the other repo (spec §9.1), critic-recall eval fixtures (spec §10.1) — the blind-critic must beat a same-context critique baseline before v2 ships.
- **Open (spec §13):** human-atom entry point (the `harvest-atoms` subcommand with `--sensor human` is the seam; the UX — CLI vs Obsidian inbox — is undecided), family mix / n_eff measurement, license and positioning.

---

## Post-final-review amendments (2026-07-05, commits 4e818f7 / aeefa4c / 0d02ece)

The whole-branch review found three defects in this plan's own sample code; the implementations were amended as follows (the task sections above are NOT retro-edited):

1. **CachedEmbed writes atomically** (`cluster.py`): parallel farm CLIs share `emb-cache.json`; writes go through a same-directory temp file + `os.replace`, and a torn/corrupt cache file reads as `{}` instead of crashing. Lost updates between concurrent writers are accepted (re-embedding is cheap); torn reads are not.
2. **`farm-init` canonicalizes `meta.hypothesis_id` from its own harvest** (`cli.py`): the `--hypothesis-id` flag is advisory; the canonical `h-…` id comes from re-observing `--hypothesis-text` as a hypothesis node. This fixes saturate-mode gap farms, which passed `c-…` claim ids (Task 11's `holeAtoms.atom_ids[i]`), silently detaching the premortem gate, CONCEDE status, refuted computation, and tripwire wiring from the farm's actual thesis node. A farm whose hypothesis text is rejected as non-self-contained refuses to start.
3. **CONCLUDE requires a blind critique on record** (`gates.py` + `cmd_gate`): `conclude_blockers`/`resolve_decision` gain `critiques: int = 0`; zero critiques blocks CONCLUDE with "no blind critique on record - an uncritiqued thesis cannot conclude". Closes the round-1-CONCLUDE path that ended a farm before any refutation ran (spec §5 Phase 3: critic runs per farm per round). No survey.js change: the blocked round-1 CONCLUDE forces CONTINUE, the critique runs, and the farm faces it in round 2.

Known-and-accepted (backlog, not amended): curator prompt lacks conceded/tripwire inputs its mandate names; `p1-farm{F}-init` sorts before `p1-framing` (harmless today, rename to `p1z-`/`p6z-` when next touched); `cmd_query` catches bare Exception; clerk scratch paths are not run-scoped; missing round≥2 ledger entries are not warned on; rival entailment-merge can alias `meta.hypothesis_id` (conservative failure; canonicalize-at-read is plan-3 work).
