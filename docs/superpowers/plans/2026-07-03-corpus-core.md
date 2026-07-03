# Corpus Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build ant-farm's data layer — atom/edge schemas, append-only event log, deterministic reducer with entailment merge, view/well stores, graph queries, retained farm transcripts (keel export), counterfactual generator, and Obsidian render.

**Architecture:** A Python package (`antfarm`) of pure functions over pydantic models. JSONL run logs are the source of truth; a deterministic reducer folds them into corpus state; Chroma and NetworkX are derived indexes rebuilt from that state. The JS workflow script (plan 2) shells into this package; nothing here calls a model.

**Tech Stack:** Python ≥3.12, uv, pydantic v2, chromadb, networkx, pytest.

**Spec:** `docs/specs/2026-07-03-ant-farm-design.md` (spec §N references below).

## Global Constraints

- **Append-only:** runs never edit history; reducer state is always recomputable from events (spec §4.1).
- **Atoms are self-contained:** "no pronouns, no unresolved references; embeddable without context (validator-enforced)" (spec §4.1).
- **IDs are content hashes, "stable across runs"** (spec §4.1): same type + normalized text ⇒ same id.
- **Supersession without deletion**; conceded hypotheses stay on the map with their died-because record (spec §4.2).
- **View admission is a computed gate** — no agent (curator included) can admit atoms (spec §4.3).
- **Warrants live on edges**; every `supports` edge requires one (spec §4.1, §7).
- **keel export schema is exact:** `{"turn", "role", "phase", "iteration", "content"}` per line, vantage manifest in `stats.json` (spec §4.5, §9.2).
- **Label discipline:** CONCEDE is a dialectical outcome, never exported as degraded; coherent-but-wrong = CONCLUDE later refuted ⇒ `coherence_label: "coherent_refuted"` (spec §9.2).
- **Re-found ≠ duplicate:** entailment-matched atoms increment `sightings` and attach the vantage (spec §4.2).
- Event filenames must sort chronologically (zero-padded round/phase prefixes, e.g. `p2-farmA-r01.jsonl`) — the reducer replays in filename order.
- Tests marked `@pytest.mark.eval` use real embedding models (slow, downloads); default `pytest` run excludes them.

---

### Task 1: Project scaffold, text normalization, content-hash IDs, self-containedness validator

**Files:**
- Create: `pyproject.toml`
- Create: `src/antfarm/__init__.py` (empty)
- Create: `src/antfarm/schema.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `normalize_text(text: str) -> str`; `atom_id(node_type: str, text: str) -> str`; `is_self_contained(text: str) -> bool`; constants `ID_PREFIX: dict[str, str]`, type aliases `NodeType`, `NodeStatus`, `EdgeRel` (all in `antfarm.schema`)

- [ ] **Step 1: Write pyproject and package skeleton**

`pyproject.toml`:

```toml
[project]
name = "antfarm"
version = "0.1.0"
description = "A surveying instrument for contested questions - corpus core"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.7",
    "chromadb>=1.0",
    "networkx>=3.3",
]

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/antfarm"]

[tool.pytest.ini_options]
addopts = "-m 'not eval'"
markers = ["eval: evaluation tests using real embedding models (slow, downloads)"]
```

Create empty `src/antfarm/__init__.py`, then run: `uv sync`
Expected: resolves and installs dependencies without error.

- [ ] **Step 2: Write the failing test**

`tests/test_schema.py`:

```python
from antfarm.schema import atom_id, is_self_contained, normalize_text


def test_normalize_collapses_whitespace_and_case():
    assert normalize_text("  Solar  is\ncheaper ") == "solar is cheaper"


def test_atom_id_stable_across_formatting():
    assert atom_id("claim", "Solar is cheaper") == atom_id("claim", "  solar   is CHEAPER ")


def test_atom_id_prefixes_by_type():
    assert atom_id("claim", "x").startswith("c-")
    assert atom_id("evidence", "x").startswith("e-")
    assert atom_id("hypothesis", "x").startswith("h-")
    assert atom_id("tripwire", "x").startswith("w-")


def test_atom_id_differs_by_type():
    assert atom_id("claim", "x") != atom_id("evidence", "x")


def test_self_contained_accepts_standalone_claims():
    assert is_self_contained("Solar LCOE fell roughly 90% between 2010 and 2020.")


def test_self_contained_rejects_unresolved_references():
    assert not is_self_contained("This proves the thesis.")
    assert not is_self_contained("It follows from the above argument.")
    assert not is_self_contained("The former option dominates.")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_schema.py -v`
Expected: FAIL with `ImportError` / `cannot import name 'atom_id'`

- [ ] **Step 4: Write minimal implementation**

`src/antfarm/schema.py`:

```python
import hashlib
import re
from typing import Literal

NodeType = Literal[
    "claim", "evidence", "tension", "crux", "hypothesis", "source", "vantage", "tripwire"
]
NodeStatus = Literal["live", "contested", "superseded", "conceded"]
EdgeRel = Literal[
    "supports", "rebuts", "undercuts", "qualifies",
    "bridges", "depends_on", "supersedes", "scored_against",
]

ID_PREFIX: dict[str, str] = {
    "claim": "c", "evidence": "e", "tension": "t", "crux": "x",
    "hypothesis": "h", "source": "s", "vantage": "v", "tripwire": "w",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def atom_id(node_type: str, text: str) -> str:
    digest = hashlib.sha256(f"{node_type}:{normalize_text(text)}".encode()).hexdigest()
    return f"{ID_PREFIX[node_type]}-{digest[:12]}"


_UNRESOLVED = re.compile(
    r"^(it|this|that|they|these|those|he|she)\b"
    r"|\b(the above|the former|the latter|as mentioned|as noted)\b",
    re.IGNORECASE,
)


def is_self_contained(text: str) -> bool:
    return _UNRESOLVED.search(text.strip()) is None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_schema.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/antfarm tests/test_schema.py
git commit -m "feat: scaffold antfarm package with content-hash ids and self-containedness validator"
```

---

### Task 2: Node and Edge schemas

**Files:**
- Modify: `src/antfarm/schema.py` (append)
- Test: `tests/test_schema.py` (append)

**Interfaces:**
- Consumes: Task 1's `atom_id`, `is_self_contained`, type aliases
- Produces: `Vantage(run, farm, family, persona, round: int, sensor: Literal["model","human"])`; `Node` (fields exactly as spec §4.1: `id, type, text, vantage, status, superseded_by, strength, diagnosticity, verified, sightings, question_id, ts`) with classmethod `Node.create(*, type, text, vantage, question_id, ts, **kwargs) -> Node` that computes `id`; `Edge(src, dst, rel, warrant, consistency, vantage, ts)`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_schema.py`:

```python
import pytest
from pydantic import ValidationError

from antfarm.schema import Edge, Node, Vantage

V = Vantage(run="r1", farm="A", family="claude", persona="procurement manager",
            round=1, sensor="model")


def _node(**kw):
    defaults = dict(type="claim", text="Solar LCOE fell 90% between 2010 and 2020.",
                    vantage=V, question_id="q-1", ts="2026-07-03T00:00:00Z")
    defaults.update(kw)
    return Node.create(**defaults)


def test_create_computes_content_hash_id():
    n = _node()
    assert n.id.startswith("c-") and len(n.id) == 14
    assert n.id == _node().id  # stable across runs


def test_node_rejects_non_self_contained_text():
    with pytest.raises(ValidationError):
        _node(text="This proves the thesis.")


def test_node_rejects_tampered_id():
    n = _node()
    with pytest.raises(ValidationError):
        Node(**{**n.model_dump(), "id": "c-000000000000"})


def test_strength_only_on_evidence():
    with pytest.raises(ValidationError):
        _node(strength=4)  # type=claim
    e = _node(type="evidence", strength=4)
    assert e.strength == 4


def test_node_defaults():
    n = _node()
    assert n.status == "live" and n.verified is False and n.sightings == 1


def test_supports_edge_requires_warrant():
    with pytest.raises(ValidationError):
        Edge(src="e-1", dst="c-1", rel="supports", vantage=V, ts="2026-07-03T00:00:00Z")
    ok = Edge(src="e-1", dst="c-1", rel="supports", warrant="cost curves license the inference",
              vantage=V, ts="2026-07-03T00:00:00Z")
    assert ok.warrant


def test_consistency_only_on_scored_against():
    with pytest.raises(ValidationError):
        Edge(src="e-1", dst="h-1", rel="rebuts", consistency="inconsistent",
             vantage=V, ts="2026-07-03T00:00:00Z")
    ok = Edge(src="e-1", dst="h-1", rel="scored_against", consistency="inconsistent",
              vantage=V, ts="2026-07-03T00:00:00Z")
    assert ok.consistency == "inconsistent"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schema.py -v`
Expected: FAIL with `ImportError: cannot import name 'Node'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/antfarm/schema.py`:

```python
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Vantage(BaseModel):
    run: str
    farm: str
    family: str
    persona: str
    round: int
    sensor: Literal["model", "human"]


class Node(BaseModel):
    id: str
    type: NodeType
    text: str
    vantage: Vantage
    status: NodeStatus = "live"
    superseded_by: Optional[str] = None
    strength: Optional[int] = Field(default=None, ge=1, le=5)
    diagnosticity: Optional[Literal["high", "med", "none"]] = None
    verified: bool = False
    sightings: int = 1
    question_id: str
    ts: str

    @field_validator("text")
    @classmethod
    def _text_self_contained(cls, v: str) -> str:
        if not is_self_contained(v):
            raise ValueError(f"atom text is not self-contained: {v[:60]!r}")
        return v

    @model_validator(mode="after")
    def _invariants(self) -> "Node":
        if self.id != atom_id(self.type, self.text):
            raise ValueError("id does not match content hash of (type, text)")
        if self.strength is not None and self.type != "evidence":
            raise ValueError("strength applies to evidence nodes only")
        return self

    @classmethod
    def create(cls, *, type: NodeType, text: str, vantage: Vantage,
               question_id: str, ts: str, **kwargs) -> "Node":
        return cls(id=atom_id(type, text), type=type, text=text, vantage=vantage,
                   question_id=question_id, ts=ts, **kwargs)


class Edge(BaseModel):
    src: str
    dst: str
    rel: EdgeRel
    warrant: Optional[str] = None
    consistency: Optional[Literal["consistent", "inconsistent", "neutral"]] = None
    vantage: Vantage
    ts: str

    @model_validator(mode="after")
    def _invariants(self) -> "Edge":
        if self.rel == "supports" and not self.warrant:
            raise ValueError("supports edges require a warrant (Toulmin, spec §4.1)")
        if self.consistency is not None and self.rel != "scored_against":
            raise ValueError("consistency applies to scored_against edges only")
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schema.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add src/antfarm/schema.py tests/test_schema.py
git commit -m "feat: Node and Edge schemas with warrant and self-containedness invariants"
```

---

### Task 3: Append-only event log

**Files:**
- Create: `src/antfarm/events.py`
- Test: `tests/test_events.py`

**Interfaces:**
- Consumes: `Node`, `Edge` from `antfarm.schema`
- Produces: `node_event(node: Node) -> dict`; `edge_event(edge: Edge) -> dict`; `status_event(node_id: str, status: str, *, ts: str, died_because: str | None = None) -> dict`; `append_events(run_dir: Path, label: str, events: list[dict]) -> Path`; `read_events(runs_root: Path) -> list[dict]` (replays every `*.jsonl` under `runs_root` in sorted path order, line order within files)

- [ ] **Step 1: Write the failing test**

`tests/test_events.py`:

```python
from antfarm.events import append_events, edge_event, node_event, read_events, status_event
from antfarm.schema import Edge, Node, Vantage

V = Vantage(run="r1", farm="A", family="claude", persona="analyst", round=1, sensor="model")


def _node(text):
    return Node.create(type="claim", text=text, vantage=V,
                       question_id="q-1", ts="2026-07-03T00:00:00Z")


def test_roundtrip_and_append_only(tmp_path):
    run_dir = tmp_path / "r1"
    n = _node("Solar LCOE fell 90% between 2010 and 2020.")
    e = Edge(src=n.id, dst="h-000000000001", rel="rebuts", vantage=V, ts="2026-07-03T00:00:00Z")

    append_events(run_dir, "p2-farmA-r01", [node_event(n)])
    append_events(run_dir, "p2-farmA-r01", [edge_event(e)])  # second append accumulates

    events = read_events(tmp_path)
    assert [ev["kind"] for ev in events] == ["node", "edge"]
    assert events[0]["payload"]["id"] == n.id


def test_replay_order_is_sorted_path_order(tmp_path):
    append_events(tmp_path / "r1", "p2-farmB-r01", [status_event("h-1", "contested", ts="t")])
    append_events(tmp_path / "r1", "p1-framing", [status_event("h-1", "live", ts="t")])
    kinds = [ev["payload"]["status"] for ev in read_events(tmp_path)]
    assert kinds == ["live", "contested"]  # p1 file replays before p2 file


def test_status_event_carries_died_because():
    ev = status_event("h-1", "conceded", ts="t", died_because="failed severity gate")
    assert ev == {"kind": "status", "payload": {
        "id": "h-1", "status": "conceded", "died_because": "failed severity gate", "ts": "t"}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'antfarm.events'`

- [ ] **Step 3: Write minimal implementation**

`src/antfarm/events.py`:

```python
import json
from pathlib import Path

from antfarm.schema import Edge, Node


def node_event(node: Node) -> dict:
    return {"kind": "node", "payload": node.model_dump()}


def edge_event(edge: Edge) -> dict:
    return {"kind": "edge", "payload": edge.model_dump()}


def status_event(node_id: str, status: str, *, ts: str,
                 died_because: str | None = None) -> dict:
    return {"kind": "status", "payload": {
        "id": node_id, "status": status, "died_because": died_because, "ts": ts}}


def append_events(run_dir: Path, label: str, events: list[dict]) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{label}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return path


def read_events(runs_root: Path) -> list[dict]:
    out: list[dict] = []
    for path in sorted(runs_root.rglob("*.jsonl")):
        with path.open(encoding="utf-8") as f:
            out.extend(json.loads(line) for line in f if line.strip())
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_events.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/antfarm/events.py tests/test_events.py
git commit -m "feat: append-only JSONL event log with deterministic replay order"
```

---

### Task 4: Reducer — fold events into corpus state

**Files:**
- Create: `src/antfarm/reduce.py`
- Test: `tests/test_reduce.py`

**Interfaces:**
- Consumes: `Node`, `Edge`, `Vantage` from `antfarm.schema`; event dicts shaped by Task 3
- Produces: `CorpusNode` (a `Node` subclass adding `vantages: list[Vantage]` and `died_because: str | None`); `Corpus(nodes: dict[str, CorpusNode], edges: list[Edge])` (pydantic model); `reduce_events(events: list[dict], matcher=None) -> Corpus` where `matcher` is any object with `find_match(node: Node, nodes: dict[str, CorpusNode]) -> str | None` (Task 5 supplies one; `None` means exact-id merge only)

- [ ] **Step 1: Write the failing test**

`tests/test_reduce.py`:

```python
from antfarm.events import edge_event, node_event, status_event
from antfarm.reduce import reduce_events
from antfarm.schema import Edge, Node, Vantage

V1 = Vantage(run="r1", farm="A", family="claude", persona="analyst", round=1, sensor="model")
V2 = Vantage(run="r1", farm="B", family="gpt", persona="skeptic", round=1, sensor="model")


def _node(text, vantage=V1, **kw):
    return Node.create(type="claim", text=text, vantage=vantage,
                       question_id="q-1", ts="2026-07-03T00:00:00Z", **kw)


def test_new_node_enters_with_one_vantage():
    n = _node("Grid storage is the binding constraint on solar buildout.")
    corpus = reduce_events([node_event(n)])
    cn = corpus.nodes[n.id]
    assert cn.sightings == 1 and cn.vantages == [V1]


def test_refound_node_is_observation_not_duplicate():
    a = _node("Grid storage is the binding constraint on solar buildout.", V1)
    b = _node("Grid storage is the binding constraint on solar buildout.", V2, verified=True)
    corpus = reduce_events([node_event(a), node_event(b)])
    assert len(corpus.nodes) == 1
    cn = corpus.nodes[a.id]
    assert cn.sightings == 2
    assert cn.vantages == [V1, V2]
    assert cn.verified is True  # verification upgrades, never downgrades


def test_supersedes_edge_marks_old_node_without_deletion():
    old = _node("Coal plants retire on a 40-year schedule.")
    new = _node("Coal plants retire on a 30-year schedule after IRA incentives.")
    sup = Edge(src=new.id, dst=old.id, rel="supersedes", vantage=V1, ts="t")
    corpus = reduce_events([node_event(old), node_event(new), edge_event(sup)])
    assert corpus.nodes[old.id].status == "superseded"
    assert corpus.nodes[old.id].superseded_by == new.id
    assert old.id in corpus.nodes  # never deleted


def test_conceded_stays_on_map_with_died_because():
    h = _node("Fusion arrives before 2035 at grid scale.")
    corpus = reduce_events([
        node_event(h),
        status_event(h.id, "conceded", ts="t", died_because="no surviving evidence path"),
    ])
    assert corpus.nodes[h.id].status == "conceded"
    assert corpus.nodes[h.id].died_because == "no surviving evidence path"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reduce.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'antfarm.reduce'`

- [ ] **Step 3: Write minimal implementation**

`src/antfarm/reduce.py`:

```python
from pydantic import BaseModel, Field

from antfarm.schema import Edge, Node, Vantage


class CorpusNode(Node):
    vantages: list[Vantage] = Field(default_factory=list)
    died_because: str | None = None


class Corpus(BaseModel):
    nodes: dict[str, CorpusNode] = Field(default_factory=dict)
    edges: list[Edge] = Field(default_factory=list)


def _observe(existing: CorpusNode, incoming: Node) -> None:
    existing.sightings += 1
    existing.vantages.append(incoming.vantage)
    existing.verified = existing.verified or incoming.verified


def reduce_events(events: list[dict], matcher=None) -> Corpus:
    corpus = Corpus()
    for ev in events:
        kind, payload = ev["kind"], ev["payload"]
        if kind == "node":
            node = Node.model_validate(payload)
            target = node.id if node.id in corpus.nodes else (
                matcher.find_match(node, corpus.nodes) if matcher else None)
            if target:
                _observe(corpus.nodes[target], node)
            else:
                corpus.nodes[node.id] = CorpusNode.model_validate(
                    {**node.model_dump(), "vantages": [node.vantage.model_dump()]})
        elif kind == "edge":
            edge = Edge.model_validate(payload)
            corpus.edges.append(edge)
            if edge.rel == "supersedes" and edge.dst in corpus.nodes:
                old = corpus.nodes[edge.dst]
                old.status = "superseded"
                old.superseded_by = edge.src
        elif kind == "status":
            target = corpus.nodes.get(payload["id"])
            if target is not None:
                target.status = payload["status"]
                target.died_because = payload.get("died_because") or target.died_because
    return corpus
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_reduce.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/antfarm/reduce.py tests/test_reduce.py
git commit -m "feat: deterministic reducer with observation merge and supersession-without-deletion"
```

---

### Task 5: Entailment matcher + merge-fidelity eval (spec §10.3)

**Files:**
- Create: `src/antfarm/cluster.py`
- Test: `tests/test_cluster.py`

**Interfaces:**
- Consumes: `Node`, `CorpusNode` types; `reduce_events(events, matcher)` from Task 4
- Produces: `EmbedFn = Callable[[list[str]], list[list[float]]]`; `cosine(a: list[float], b: list[float]) -> float`; `EmbeddingMatcher(embed_fn: EmbedFn, threshold: float = 0.85)` with `.find_match(node, nodes) -> str | None` (matches only same `type` + `question_id`, caches embeddings); `entailment_clusters(texts: list[str], embed_fn: EmbedFn, threshold: float = 0.85) -> list[list[int]]` (greedy single-link; the certificate plan counts singleton clusters from this)

- [ ] **Step 1: Write the failing test**

`tests/test_cluster.py`:

```python
import pytest

from antfarm.cluster import EmbeddingMatcher, cosine, entailment_clusters
from antfarm.events import node_event
from antfarm.reduce import reduce_events
from antfarm.schema import Node, Vantage

V = Vantage(run="r1", farm="A", family="claude", persona="analyst", round=1, sensor="model")

# Deterministic fake: identical vector for texts sharing a canned key, orthogonal otherwise.
_CANNED = {
    "grid storage is the binding constraint on solar buildout.": [1.0, 0.0, 0.0],
    "storage capacity, not panel cost, now limits solar deployment.": [0.96, 0.28, 0.0],
    "coal plants retire on a 40-year schedule.": [0.0, 1.0, 0.0],
}


def fake_embed(texts: list[str]) -> list[list[float]]:
    return [_CANNED[t.lower()] for t in texts]


def _node(text, node_type="claim"):
    return Node.create(type=node_type, text=text, vantage=V,
                       question_id="q-1", ts="2026-07-03T00:00:00Z")


def test_cosine():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_paraphrase_merges_as_observation():
    a = _node("Grid storage is the binding constraint on solar buildout.")
    b = _node("Storage capacity, not panel cost, now limits solar deployment.")
    matcher = EmbeddingMatcher(fake_embed, threshold=0.85)
    corpus = reduce_events([node_event(a), node_event(b)], matcher=matcher)
    assert len(corpus.nodes) == 1
    assert corpus.nodes[a.id].sightings == 2


def test_distinct_claim_does_not_merge():
    a = _node("Grid storage is the binding constraint on solar buildout.")
    b = _node("Coal plants retire on a 40-year schedule.")
    matcher = EmbeddingMatcher(fake_embed, threshold=0.85)
    corpus = reduce_events([node_event(a), node_event(b)], matcher=matcher)
    assert len(corpus.nodes) == 2


def test_never_matches_across_types():
    a = _node("Grid storage is the binding constraint on solar buildout.")
    b = _node("Storage capacity, not panel cost, now limits solar deployment.", "evidence")
    matcher = EmbeddingMatcher(fake_embed, threshold=0.85)
    corpus = reduce_events([node_event(a), node_event(b)], matcher=matcher)
    assert len(corpus.nodes) == 2


def test_entailment_clusters_groups_paraphrases():
    texts = ["Grid storage is the binding constraint on solar buildout.",
             "Storage capacity, not panel cost, now limits solar deployment.",
             "Coal plants retire on a 40-year schedule."]
    clusters = entailment_clusters(texts, fake_embed, threshold=0.85)
    assert sorted(map(sorted, clusters)) == [[0, 1], [2]]


PARAPHRASE_PAIRS = [
    ("Home solar panels pay for themselves within ten years in most US states.",
     "In the majority of US states, rooftop solar recoups its cost in under a decade."),
    ("Remote work reduces total carbon emissions from commuting.",
     "Commuting emissions fall when employees work from home."),
]
DISTINCT_PAIRS = [
    ("Home solar panels pay for themselves within ten years in most US states.",
     "Utility-scale solar is cheaper per watt than rooftop solar."),
    ("Remote work reduces total carbon emissions from commuting.",
     "Remote work increases residential energy consumption."),
]


@pytest.mark.eval
def test_merge_fidelity_with_real_embeddings():
    """Spec §10.3: paraphrases must merge; genuine variants must separate."""
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
    ef = DefaultEmbeddingFunction()
    embed = lambda texts: [list(map(float, v)) for v in ef(texts)]
    for a, b in PARAPHRASE_PAIRS:
        assert len(entailment_clusters([a, b], embed, threshold=0.85)) == 1, (a, b)
    for a, b in DISTINCT_PAIRS:
        assert len(entailment_clusters([a, b], embed, threshold=0.85)) == 2, (a, b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cluster.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'antfarm.cluster'` (the `eval` test is excluded by default)

- [ ] **Step 3: Write minimal implementation**

`src/antfarm/cluster.py`:

```python
import math
from typing import Callable

from antfarm.reduce import CorpusNode
from antfarm.schema import Node

EmbedFn = Callable[[list[str]], list[list[float]]]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class EmbeddingMatcher:
    def __init__(self, embed_fn: EmbedFn, threshold: float = 0.85):
        self.embed_fn = embed_fn
        self.threshold = threshold
        self._cache: dict[str, list[float]] = {}

    def _vec(self, text: str) -> list[float]:
        if text not in self._cache:
            self._cache[text] = self.embed_fn([text])[0]
        return self._cache[text]

    def find_match(self, node: Node, nodes: dict[str, CorpusNode]) -> str | None:
        query = self._vec(node.text)
        best_id, best_score = None, 0.0
        for candidate in nodes.values():
            if candidate.type != node.type or candidate.question_id != node.question_id:
                continue
            score = cosine(query, self._vec(candidate.text))
            if score > best_score:
                best_id, best_score = candidate.id, score
        return best_id if best_score >= self.threshold else None


def entailment_clusters(texts: list[str], embed_fn: EmbedFn,
                        threshold: float = 0.85) -> list[list[int]]:
    vecs = embed_fn(texts)
    clusters: list[list[int]] = []
    for i, vec in enumerate(vecs):
        for cluster in clusters:
            if any(cosine(vec, vecs[j]) >= threshold for j in cluster):
                cluster.append(i)
                break
        else:
            clusters.append([i])
    return clusters
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cluster.py -v`
Expected: 5 passed, 1 deselected

- [ ] **Step 5: Run the merge-fidelity eval**

Run: `uv run pytest tests/test_cluster.py -m eval -v`
Expected: 1 passed (first run downloads the default ONNX embedding model). If a pair fails at 0.85, tune the threshold and record the value — this eval is exactly how spec §13.1 says the threshold gets decided.

- [ ] **Step 6: Commit**

```bash
git add src/antfarm/cluster.py tests/test_cluster.py
git commit -m "feat: entailment matcher and clustering with merge-fidelity eval"
```

---

### Task 6: Graph queries — centrality, cruxes, undercutters, blast radius

**Files:**
- Create: `src/antfarm/graph.py`
- Test: `tests/test_graph.py`

**Interfaces:**
- Consumes: `Corpus`, `CorpusNode`, `Edge` from Task 4
- Produces: `build_graph(corpus: Corpus) -> nx.MultiDiGraph`; `centrality(g: nx.MultiDiGraph) -> dict[str, float]`; `extract_cruxes(corpus: Corpus, cent: dict[str, float], top_k: int = 5) -> list[str]`; `unsublated_undercutters(corpus: Corpus) -> list[tuple[str, str]]`; `blast_radius(g: nx.MultiDiGraph, node_id: str) -> set[str]`

- [ ] **Step 1: Write the failing test**

`tests/test_graph.py`:

```python
from antfarm.graph import (blast_radius, build_graph, centrality,
                           extract_cruxes, unsublated_undercutters)
from antfarm.reduce import Corpus, CorpusNode
from antfarm.schema import Edge, Vantage, atom_id

V = Vantage(run="r1", farm="A", family="claude", persona="analyst", round=1, sensor="model")


def _cn(text, node_type="claim", **kw):
    nid = atom_id(node_type, text)
    return nid, CorpusNode(id=nid, type=node_type, text=text, vantage=V, vantages=[V],
                           question_id="q-1", ts="t", **kw)


def _edge(src, dst, rel, **kw):
    return Edge(src=src, dst=dst, rel=rel, vantage=V, ts="t", **kw)


def _corpus():
    a_id, a = _cn("Solar deployment doubles every three years.")
    b_id, b = _cn("Grid storage capacity limits solar deployment growth.", status="contested")
    c_id, c = _cn("Battery costs fall 15% per doubling of production.")
    d_id, d = _cn("Undercutting: deployment statistics conflate contracted and installed capacity.")
    corpus = Corpus(nodes={a_id: a, b_id: b, c_id: c, d_id: d}, edges=[
        _edge(a_id, b_id, "depends_on"),
        _edge(b_id, c_id, "depends_on"),
        _edge(d_id, a_id, "undercuts"),
    ])
    return corpus, a_id, b_id, c_id, d_id


def test_build_graph_has_all_nodes_and_edges():
    corpus, *_ = _corpus()
    g = build_graph(corpus)
    assert g.number_of_nodes() == 4 and g.number_of_edges() == 3


def test_blast_radius_walks_depends_on_upstream():
    corpus, a_id, b_id, c_id, d_id = _corpus()
    g = build_graph(corpus)
    # c fires -> b depends on c, a depends on b: both affected; d does not depend on c
    assert blast_radius(g, c_id) == {a_id, b_id}
    assert blast_radius(g, a_id) == set()


def test_extract_cruxes_ranks_contested_by_centrality():
    corpus, a_id, b_id, c_id, d_id = _corpus()
    cent = centrality(build_graph(corpus))
    assert extract_cruxes(corpus, cent) == [b_id]  # only contested node


def test_unsublated_undercutters_found_and_cleared():
    corpus, a_id, b_id, c_id, d_id = _corpus()
    assert unsublated_undercutters(corpus) == [(d_id, a_id)]
    # a rebuttal against the undercutter clears it
    corpus.edges.append(_edge(a_id, d_id, "rebuts"))
    assert unsublated_undercutters(corpus) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'antfarm.graph'`

- [ ] **Step 3: Write minimal implementation**

`src/antfarm/graph.py`:

```python
import networkx as nx

from antfarm.reduce import Corpus


def build_graph(corpus: Corpus) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for nid, node in corpus.nodes.items():
        g.add_node(nid, type=node.type, status=node.status)
    for edge in corpus.edges:
        if edge.src in g and edge.dst in g:
            g.add_edge(edge.src, edge.dst, rel=edge.rel)
    return g


def centrality(g: nx.MultiDiGraph) -> dict[str, float]:
    return nx.betweenness_centrality(nx.Graph(g))


def extract_cruxes(corpus: Corpus, cent: dict[str, float], top_k: int = 5) -> list[str]:
    contested = [nid for nid, node in corpus.nodes.items()
                 if node.status == "contested" or node.type in ("crux", "tension")]
    contested.sort(key=lambda nid: cent.get(nid, 0.0), reverse=True)
    return contested[:top_k]


def unsublated_undercutters(corpus: Corpus) -> list[tuple[str, str]]:
    answered = {edge.dst for edge in corpus.edges
                if edge.rel in ("rebuts", "supersedes", "qualifies")}
    out = []
    for edge in corpus.edges:
        if edge.rel != "undercuts":
            continue
        src, dst = corpus.nodes.get(edge.src), corpus.nodes.get(edge.dst)
        if (src and dst and src.status == "live" and dst.status == "live"
                and edge.src not in answered):
            out.append((edge.src, edge.dst))
    return out


def blast_radius(g: nx.MultiDiGraph, node_id: str) -> set[str]:
    dep = nx.DiGraph(
        (u, v) for u, v, data in g.edges(data=True) if data["rel"] == "depends_on")
    if node_id not in dep:
        return set()
    return nx.ancestors(dep, node_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/antfarm/graph.py tests/test_graph.py
git commit -m "feat: graph queries for centrality, cruxes, undercutters, blast radius"
```

---

### Task 7: The view gate (computed admission, spec §4.3)

**Files:**
- Modify: `src/antfarm/graph.py` (append)
- Test: `tests/test_graph.py` (append)

**Interfaces:**
- Consumes: `Corpus` (Task 4), `centrality` output (Task 6)
- Produces: `compute_view(corpus: Corpus, cent: dict[str, float], centrality_floor: float = 0.0) -> set[str]` — admission = `status == "live"` AND `verified` AND `diagnosticity != "none"` AND centrality ≥ floor. Nothing else can admit an atom.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_graph.py`:

```python
from antfarm.graph import compute_view


def test_view_gate_admission_rules():
    corpus = Corpus()
    rows = [
        ("Verified live claims about solar economics enter the view.", dict(verified=True), True),
        ("Unverified claims about solar economics stay in the well.", dict(verified=False), False),
        ("Contested claims about solar economics stay in the well.",
         dict(verified=True, status="contested"), False),
        ("Superseded claims about solar economics stay in the well.",
         dict(verified=True, status="superseded"), False),
    ]
    expected = set()
    for text, kw, admitted in rows:
        nid, cn = _cn(text, **kw)
        corpus.nodes[nid] = cn
        if admitted:
            expected.add(nid)
    assert compute_view(corpus, cent={}) == expected


def test_view_gate_excludes_non_diagnostic_evidence():
    corpus = Corpus()
    nid, cn = _cn("Both hypotheses predict rising battery production.",
                  node_type="evidence", verified=True, diagnosticity="none")
    corpus.nodes[nid] = cn
    assert compute_view(corpus, cent={}) == set()


def test_view_gate_centrality_floor():
    corpus = Corpus()
    nid, cn = _cn("Verified live claims about solar economics enter the view.", verified=True)
    corpus.nodes[nid] = cn
    assert compute_view(corpus, cent={nid: 0.1}, centrality_floor=0.2) == set()
    assert compute_view(corpus, cent={nid: 0.3}, centrality_floor=0.2) == {nid}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_view'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/antfarm/graph.py`:

```python
def compute_view(corpus: Corpus, cent: dict[str, float],
                 centrality_floor: float = 0.0) -> set[str]:
    return {
        nid for nid, node in corpus.nodes.items()
        if node.status == "live"
        and node.verified
        and node.diagnosticity != "none"
        and cent.get(nid, 0.0) >= centrality_floor
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/antfarm/graph.py tests/test_graph.py
git commit -m "feat: computed view gate - live, verified, diagnostic, above centrality floor"
```

---

### Task 8: Chroma stores — view/well collections with routing

**Files:**
- Create: `src/antfarm/stores.py`
- Test: `tests/test_stores.py`

**Interfaces:**
- Consumes: `Corpus`, `CorpusNode` (Task 4); `compute_view` output (Task 7)
- Produces: `CorpusStore(client: chromadb.ClientAPI, embed_fn=None)` with classmethod `CorpusStore.persistent(persist_dir: Path, embed_fn=None) -> CorpusStore`, `.rebuild(corpus: Corpus, view_ids: set[str]) -> None` (drops and recreates both collections — derived index, source of truth is the event log), `.query(collection: str, text: str, n: int = 8, where: dict | None = None) -> list[dict]` returning `[{"id", "text", "metadata", "distance"}]`

- [ ] **Step 1: Write the failing test**

`tests/test_stores.py`:

```python
import chromadb

from antfarm.reduce import Corpus, CorpusNode
from antfarm.schema import Vantage, atom_id
from antfarm.stores import CorpusStore

V = Vantage(run="r1", farm="A", family="claude", persona="analyst", round=2, sensor="model")


class HashEmbed(chromadb.EmbeddingFunction):
    """Deterministic 8-dim embedding from character trigram hashes - no model download."""

    def __call__(self, input):
        out = []
        for text in input:
            vec = [0.0] * 8
            for i in range(len(text) - 2):
                vec[hash(text[i:i + 3]) % 8] += 1.0
            out.append(vec)
        return out


def _corpus():
    corpus = Corpus()
    for text, verified in [
        ("Grid storage capacity limits solar deployment growth.", True),
        ("Battery costs fall 15% per doubling of production.", False),
    ]:
        nid = atom_id("claim", text)
        corpus.nodes[nid] = CorpusNode(id=nid, type="claim", text=text, vantage=V,
                                       vantages=[V], verified=verified,
                                       question_id="q-1", ts="t")
    return corpus


def _store():
    return CorpusStore(chromadb.EphemeralClient(), embed_fn=HashEmbed())


def test_routing_well_gets_everything_view_gets_subset():
    corpus = _corpus()
    view_ids = {nid for nid, n in corpus.nodes.items() if n.verified}
    store = _store()
    store.rebuild(corpus, view_ids)
    assert len(store.query("well", "solar", n=10)) == 2
    view_hits = store.query("view", "solar", n=10)
    assert [h["id"] for h in view_hits] == list(view_ids)


def test_metadata_filters():
    corpus = _corpus()
    store = _store()
    store.rebuild(corpus, set(corpus.nodes))
    hits = store.query("well", "solar", n=10, where={"verified": True})
    assert len(hits) == 1 and hits[0]["metadata"]["family"] == "claude"


def test_rebuild_is_idempotent():
    corpus = _corpus()
    store = _store()
    store.rebuild(corpus, set())
    store.rebuild(corpus, set())  # must not raise or duplicate
    assert len(store.query("well", "solar", n=10)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stores.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'antfarm.stores'`

- [ ] **Step 3: Write minimal implementation**

`src/antfarm/stores.py`:

```python
from pathlib import Path

import chromadb

from antfarm.reduce import Corpus, CorpusNode


def _metadata(node: CorpusNode) -> dict:
    return {
        "type": node.type,
        "status": node.status,
        "verified": node.verified,
        "sightings": node.sightings,
        "question_id": node.question_id,
        "farm": node.vantage.farm,
        "family": node.vantage.family,
        "persona": node.vantage.persona,
        "round": node.vantage.round,
        "sensor": node.vantage.sensor,
    }


class CorpusStore:
    def __init__(self, client: chromadb.ClientAPI, embed_fn=None):
        self.client = client
        self.embed_fn = embed_fn

    @classmethod
    def persistent(cls, persist_dir: Path, embed_fn=None) -> "CorpusStore":
        return cls(chromadb.PersistentClient(path=str(persist_dir)), embed_fn=embed_fn)

    def _fresh_collection(self, name: str):
        try:
            self.client.delete_collection(name)
        except Exception:
            pass
        kwargs = {"embedding_function": self.embed_fn} if self.embed_fn else {}
        return self.client.create_collection(name, **kwargs)

    def rebuild(self, corpus: Corpus, view_ids: set[str]) -> None:
        for name, ids in (("well", list(corpus.nodes)), ("view", list(view_ids))):
            collection = self._fresh_collection(name)
            if ids:
                collection.add(
                    ids=ids,
                    documents=[corpus.nodes[nid].text for nid in ids],
                    metadatas=[_metadata(corpus.nodes[nid]) for nid in ids],
                )

    def query(self, collection: str, text: str, n: int = 8,
              where: dict | None = None) -> list[dict]:
        kwargs = {"embedding_function": self.embed_fn} if self.embed_fn else {}
        col = self.client.get_collection(collection, **kwargs)
        res = col.query(query_texts=[text], n_results=n, where=where)
        return [
            {"id": i, "text": doc, "metadata": meta, "distance": dist}
            for i, doc, meta, dist in zip(
                res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stores.py -v`
Expected: 3 passed. (If chromadb rejects the `HashEmbed` stub, consult its installed `EmbeddingFunction` ABC and add the required methods to the test stub — the store code itself stays unchanged.)

- [ ] **Step 5: Commit**

```bash
git add src/antfarm/stores.py tests/test_stores.py
git commit -m "feat: chroma view/well stores with vantage metadata and routing"
```

---

### Task 9: Transcript writer — keel export (spec §4.5, §9.2)

**Files:**
- Create: `src/antfarm/transcript.py`
- Test: `tests/test_transcript.py`

**Interfaces:**
- Consumes: `Vantage` from `antfarm.schema`
- Produces: `Turn(turn: int, role: Literal["user","assistant","system"], phase: Literal["sublate","expand","compress","critique"] | None, iteration: int, content: str)`; `Outcome(decision: Literal["CONCLUDE","CONCEDE","ELEVATE"], ledger_clean: bool, refuted: bool = False, died_because: str | None = None)`; `coherence_label(outcome: Outcome) -> str`; `write_transcript(farm_dir: Path, turns: list[Turn], vantage: Vantage, outcome: Outcome) -> tuple[Path, Path]` writing `trace.jsonl` + `stats.json`

- [ ] **Step 1: Write the failing test**

`tests/test_transcript.py`:

```python
import json

from antfarm.schema import Vantage
from antfarm.transcript import Outcome, Turn, coherence_label, write_transcript

V = Vantage(run="r1", farm="A", family="claude", persona="analyst", round=3, sensor="model")

TURNS = [
    Turn(turn=0, role="user", phase=None, iteration=1, content="Question: is rooftop solar a good investment?"),
    Turn(turn=1, role="assistant", phase="expand", iteration=1, content="Payback periods have fallen below ten years in most states."),
    Turn(turn=2, role="assistant", phase="compress", iteration=1, content="Thesis: rooftop solar pays back in under a decade."),
    Turn(turn=3, role="assistant", phase="sublate", iteration=2, content="The critique about net-metering rollbacks survives; qualifying the thesis to net-metering states."),
]


def test_trace_jsonl_matches_keel_schema_exactly(tmp_path):
    outcome = Outcome(decision="CONCLUDE", ledger_clean=True)
    trace_path, stats_path = write_transcript(tmp_path / "farmA", TURNS, V, outcome)
    lines = [json.loads(l) for l in trace_path.read_text().splitlines()]
    assert len(lines) == 4
    # exact keel traces/ schema: these five keys, no others
    assert all(set(l) == {"turn", "role", "phase", "iteration", "content"} for l in lines)
    assert lines[3] == {"turn": 3, "role": "assistant", "phase": "sublate",
                        "iteration": 2, "content": TURNS[3].content}


def test_stats_manifest_carries_vantage_outcome_label(tmp_path):
    outcome = Outcome(decision="CONCLUDE", ledger_clean=True, refuted=True)
    _, stats_path = write_transcript(tmp_path / "farmA", TURNS, V, outcome)
    stats = json.loads(stats_path.read_text())
    assert stats["vantage"]["farm"] == "A"
    assert stats["outcome"]["decision"] == "CONCLUDE"
    assert stats["coherence_label"] == "coherent_refuted"
    assert stats["turns"] == 4 and stats["iterations"] == 2
    assert stats["approx_tokens"] > 0


def test_label_discipline():
    # spec 9.2: CONCEDE is a dialectical outcome, never exported as degraded
    assert coherence_label(Outcome(decision="CONCEDE", ledger_clean=True,
                                   died_because="rival explained the evidence")) == "conceded"
    assert coherence_label(Outcome(decision="CONCLUDE", ledger_clean=True)) == "coherent"
    assert coherence_label(Outcome(decision="CONCLUDE", ledger_clean=True,
                                   refuted=True)) == "coherent_refuted"
    assert coherence_label(Outcome(decision="ELEVATE", ledger_clean=False)) == "elevated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_transcript.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'antfarm.transcript'`

- [ ] **Step 3: Write minimal implementation**

`src/antfarm/transcript.py`:

```python
import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from antfarm.schema import Vantage


class Turn(BaseModel):
    turn: int
    role: Literal["user", "assistant", "system"]
    phase: Optional[Literal["sublate", "expand", "compress", "critique"]]
    iteration: int
    content: str


class Outcome(BaseModel):
    decision: Literal["CONCLUDE", "CONCEDE", "ELEVATE"]
    ledger_clean: bool
    refuted: bool = False
    died_because: Optional[str] = None


def coherence_label(outcome: Outcome) -> str:
    if outcome.decision == "CONCLUDE":
        return "coherent_refuted" if outcome.refuted else "coherent"
    if outcome.decision == "CONCEDE":
        return "conceded"
    return "elevated"


def write_transcript(farm_dir: Path, turns: list[Turn], vantage: Vantage,
                     outcome: Outcome) -> tuple[Path, Path]:
    farm_dir.mkdir(parents=True, exist_ok=True)
    trace_path = farm_dir / "trace.jsonl"
    with trace_path.open("w", encoding="utf-8") as f:
        for t in turns:
            f.write(json.dumps(t.model_dump(), ensure_ascii=False) + "\n")
    stats = {
        "vantage": vantage.model_dump(),
        "outcome": outcome.model_dump(),
        "coherence_label": coherence_label(outcome),
        "turns": len(turns),
        "iterations": max((t.iteration for t in turns), default=0),
        "approx_tokens": sum(len(t.content) for t in turns) // 4,
    }
    stats_path = farm_dir / "stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2))
    return trace_path, stats_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_transcript.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/antfarm/transcript.py tests/test_transcript.py
git commit -m "feat: retained farm transcripts in keel traces/ schema with label discipline"
```

---

### Task 10: Counterfactual generator — shuffle and graft (spec §9.2)

persona-swap requires regeneration by a model and belongs to the pipeline plan; shuffle and graft are pure transforms and land here.

**Files:**
- Create: `src/antfarm/counterfactual.py`
- Test: `tests/test_counterfactual.py`

**Interfaces:**
- Consumes: `Turn` from Task 9
- Produces: `shuffle_turns(turns: list[Turn], seed: int) -> list[Turn]` (deterministic permutation, `turn` indices renumbered 0..n-1); `graft(host: list[Turn], donor: list[Turn], start_iteration: int) -> list[Turn]` (host turns with `iteration < start_iteration` + donor turns with `iteration >= start_iteration`, renumbered)

- [ ] **Step 1: Write the failing test**

`tests/test_counterfactual.py`:

```python
from antfarm.counterfactual import graft, shuffle_turns
from antfarm.transcript import Turn


def _turns(prefix, n_iterations=3, per_iteration=2):
    turns, i = [], 0
    for it in range(1, n_iterations + 1):
        for k in range(per_iteration):
            turns.append(Turn(turn=i, role="assistant", phase="expand", iteration=it,
                              content=f"{prefix} iteration {it} step {k}"))
            i += 1
    return turns


def test_shuffle_is_deterministic_and_renumbered():
    turns = _turns("host")
    a = shuffle_turns(turns, seed=7)
    b = shuffle_turns(turns, seed=7)
    assert [t.content for t in a] == [t.content for t in b]  # deterministic
    assert [t.turn for t in a] == list(range(6))             # renumbered
    assert sorted(t.content for t in a) == sorted(t.content for t in turns)  # same multiset
    assert [t.content for t in a] != [t.content for t in turns]  # actually permuted
    assert [t.content for t in turns] == [f"host iteration {it} step {k}"
                                          for it in (1, 2, 3) for k in (0, 1)]  # input untouched


def test_graft_splices_at_iteration_boundary():
    host, donor = _turns("host"), _turns("donor")
    grafted = graft(host, donor, start_iteration=3)
    assert [t.content for t in grafted] == [
        "host iteration 1 step 0", "host iteration 1 step 1",
        "host iteration 2 step 0", "host iteration 2 step 1",
        "donor iteration 3 step 0", "donor iteration 3 step 1",
    ]
    assert [t.turn for t in grafted] == list(range(6))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_counterfactual.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'antfarm.counterfactual'`

- [ ] **Step 3: Write minimal implementation**

`src/antfarm/counterfactual.py`:

```python
import random

from antfarm.transcript import Turn


def _renumber(turns: list[Turn]) -> list[Turn]:
    return [t.model_copy(update={"turn": i}) for i, t in enumerate(turns)]


def shuffle_turns(turns: list[Turn], seed: int) -> list[Turn]:
    shuffled = list(turns)
    random.Random(seed).shuffle(shuffled)
    return _renumber(shuffled)


def graft(host: list[Turn], donor: list[Turn], start_iteration: int) -> list[Turn]:
    kept = [t for t in host if t.iteration < start_iteration]
    spliced = [t for t in donor if t.iteration >= start_iteration]
    return _renumber(kept + spliced)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_counterfactual.py -v`
Expected: 2 passed. (If seed 7 happens to produce the identity permutation on 6 items, pick another seed in the test — the assertion `!= original order` is the guard.)

- [ ] **Step 5: Commit**

```bash
git add src/antfarm/counterfactual.py tests/test_counterfactual.py
git commit -m "feat: shuffle and graft counterfactuals - ground truth by construction"
```

---

### Task 11: Obsidian render (spec §4.4)

**Files:**
- Create: `src/antfarm/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `Corpus` (Task 4), view id set (Task 7)
- Produces: `render_obsidian(corpus: Corpus, view_ids: set[str], out_dir: Path) -> list[Path]` — one markdown page per view node: frontmatter (`type`, `status`, `verified`, `sightings`), atom text, `## Edges` with `[[wikilinks]]`, `## Standing challenges` listing incoming `rebuts`/`undercuts` edges from any well node (spec §4.3: every view node is one edge away from its standing challenges)

- [ ] **Step 1: Write the failing test**

`tests/test_render.py`:

```python
from antfarm.reduce import Corpus, CorpusNode
from antfarm.render import render_obsidian
from antfarm.schema import Edge, Vantage, atom_id

V = Vantage(run="r1", farm="A", family="claude", persona="analyst", round=1, sensor="model")


def _cn(text, node_type="claim", **kw):
    nid = atom_id(node_type, text)
    return nid, CorpusNode(id=nid, type=node_type, text=text, vantage=V, vantages=[V],
                           question_id="q-1", ts="t", **kw)


def test_render_pages_edges_and_standing_challenges(tmp_path):
    a_id, a = _cn("Grid storage capacity limits solar deployment growth.", verified=True)
    e_id, e = _cn("Battery production doubled between 2023 and 2025.",
                  node_type="evidence", verified=True)
    u_id, u = _cn("Deployment statistics conflate contracted and installed capacity.")
    corpus = Corpus(nodes={a_id: a, e_id: e, u_id: u}, edges=[
        Edge(src=e_id, dst=a_id, rel="supports", warrant="production growth bounds deployment",
             vantage=V, ts="t"),
        Edge(src=u_id, dst=a_id, rel="undercuts", vantage=V, ts="t"),
    ])
    view_ids = {a_id, e_id}  # undercutter is well-only

    paths = render_obsidian(corpus, view_ids, tmp_path)
    assert sorted(p.name for p in paths) == sorted(f"{nid}.md" for nid in view_ids)

    page = (tmp_path / f"{a_id}.md").read_text()
    assert "status: live" in page and "verified: true" in page
    assert a.text in page
    assert f"[[{e_id}]]" in page and "production growth bounds deployment" in page
    # standing challenge from a non-view node still appears (one edge away, spec 4.3)
    assert f"undercut by [[{u_id}]]" in page
    assert u.text in page
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'antfarm.render'`

- [ ] **Step 3: Write minimal implementation**

`src/antfarm/render.py`:

```python
from pathlib import Path

from antfarm.reduce import Corpus

_CHALLENGE_VERB = {"rebuts": "rebutted by", "undercuts": "undercut by"}


def _page(corpus: Corpus, nid: str) -> str:
    node = corpus.nodes[nid]
    lines = [
        "---",
        f"type: {node.type}",
        f"status: {node.status}",
        f"verified: {str(node.verified).lower()}",
        f"sightings: {node.sightings}",
        "---",
        "",
        node.text,
        "",
    ]
    outgoing = [e for e in corpus.edges if e.src == nid]
    incoming = [e for e in corpus.edges if e.dst == nid]
    plain = [e for e in outgoing + incoming
             if e.rel not in _CHALLENGE_VERB or e.src == nid]
    if plain:
        lines.append("## Edges")
        for e in plain:
            other = e.dst if e.src == nid else e.src
            entry = f"- {e.rel} → [[{other}]]" if e.src == nid else f"- {e.rel} ← [[{other}]]"
            if e.warrant:
                entry += f" — {e.warrant}"
            lines.append(entry)
        lines.append("")
    challenges = [e for e in incoming if e.rel in _CHALLENGE_VERB]
    if challenges:
        lines.append("## Standing challenges")
        for e in challenges:
            challenger = corpus.nodes.get(e.src)
            text = f": {challenger.text}" if challenger else ""
            lines.append(f"- {_CHALLENGE_VERB[e.rel]} [[{e.src}]]{text}")
        lines.append("")
    return "\n".join(lines)


def render_obsidian(corpus: Corpus, view_ids: set[str], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for nid in sorted(view_ids):
        path = out_dir / f"{nid}.md"
        path.write_text(_page(corpus, nid), encoding="utf-8")
        paths.append(path)
    return paths
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_render.py -v`
Expected: 1 passed

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: all tests pass (eval tests deselected by default)

- [ ] **Step 6: Commit**

```bash
git add src/antfarm/render.py tests/test_render.py
git commit -m "feat: obsidian render with wikilink edges and standing challenges"
```

---

## Deferred to later plans

- **Plan 2 (survey pipeline):** the `workflows/survey.js` orchestrator, the seven agent definitions, phases 0–7, schema-forcing at `agent()` calls (pydantic models export via `.model_json_schema()`), persona-swap counterfactual (needs generation), CONCLUDE gates, R/E/C bands.
- **Plan 3 (coverage certificate):** Good-Turing/Chao1 estimators over `entailment_clusters` output, rarefaction curve, correlation discount / n_eff, Zwicky grid recall, certificate calibration eval (spec §10.2).
- **Plan 4 (dialectic-plugin v2):** the deletions and consumer changes in the other repo (spec §9.1), critic-recall eval fixtures (spec §10.1).
