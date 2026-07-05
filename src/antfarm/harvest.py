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
