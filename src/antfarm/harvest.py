"""Emission -> event conversion. Stamps vantage and ts, computes content-hash
ids, resolves edge references (batch text | corpus text | corpus id), rejects
non-self-contained atoms, and renders scout output into transcript turns."""

import re

from pydantic import BaseModel, Field, ValidationError

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


def critique_harvest(report: CritiqueReport, *, vantage: Vantage, corpus: Corpus,
                     hypothesis_id: str, question_id: str, ts: str,
                     start_turn: int) -> HarvestResult:
    rel_for: dict[str, str] = {"rebutting": "rebuts", "undercutting": "undercuts"}
    atoms = [AtomEmission(type="claim", text=f.text) for f in report.findings]
    edges = [EdgeEmission(src=f.text, dst=f.target_text,
                          rel=rel_for[f.classification])  # type: ignore
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


def framing_harvest(output: FramingOutput, *, vantage: Vantage, question_id: str,
                    ts: str) -> tuple[HarvestResult, list[dict]]:
    atoms = [AtomEmission(type="hypothesis", text=r.text) for r in output.rivals]
    result = _convert(atoms, [], vantage=vantage, corpus=Corpus(),
                      question_id=question_id, ts=ts)
    accepted_ids = set(result.atom_ids)
    rivals = [{"id": atom_id("hypothesis", r.text), "text": r.text, "is_null": r.is_null}
              for r in output.rivals
              if atom_id("hypothesis", r.text) in accepted_ids]
    return result, rivals


def stitch_harvest(output: StitchOutput, *, vantage: Vantage, corpus: Corpus,
                   question_id: str, ts: str) -> HarvestResult:
    atoms = [a for inv in output.investigations for a in inv.atoms]
    edges = [e for inv in output.investigations for e in inv.edges]
    result = _convert(atoms, edges, vantage=vantage, corpus=corpus,
                      question_id=question_id, ts=ts)
    # resolve ACH refs against accepted atoms only: a rejected atom produced no
    # node event, so resolving against it would emit a scored_against edge to a
    # node that never exists - phantom evidence that ach_scores would count.
    accepted_ids = set(result.atom_ids)
    batch = {normalize_text(a.text): a for a in atoms
             if atom_id(a.type, a.text) in accepted_ids}
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


def verify_harvest(results: list[VerificationResult], *, corpus: Corpus,
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
