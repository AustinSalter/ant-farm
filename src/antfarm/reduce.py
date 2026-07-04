from pydantic import BaseModel, Field

from antfarm.schema import Edge, Node, Vantage

_DIAG_RANK = {None: 0, "none": 1, "med": 2, "high": 3}


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
    if incoming.strength is not None:
        existing.strength = max(existing.strength or 0, incoming.strength)
    if _DIAG_RANK[incoming.diagnosticity] > _DIAG_RANK[existing.diagnosticity]:
        existing.diagnosticity = incoming.diagnosticity


def _apply_supersede(corpus: Corpus, edge: Edge) -> bool:
    old = corpus.nodes.get(edge.dst)
    if old is None:
        return False
    old.status = "superseded"
    old.superseded_by = edge.src
    return True


def _apply_status(corpus: Corpus, payload: dict) -> bool:
    target = corpus.nodes.get(payload["id"])
    if target is None:
        return False
    target.status = payload["status"]
    target.died_because = payload.get("died_because") or target.died_because
    return True


def reduce_events(events: list[dict], matcher=None) -> Corpus:
    corpus = Corpus()
    deferred: list[dict] = []  # supersedes/status whose target node hasn't been seen yet
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
            if edge.rel == "supersedes" and not _apply_supersede(corpus, edge):
                deferred.append(ev)
        elif kind == "status":
            if not _apply_status(corpus, payload):
                deferred.append(ev)
        else:
            raise ValueError(f"unknown event kind: {kind!r}")

    # Re-apply deferred events and track failures
    unresolved_ids: set[str] = set()
    for ev in deferred:
        if ev["kind"] == "edge":
            edge = Edge.model_validate(ev["payload"])
            if not _apply_supersede(corpus, edge):
                unresolved_ids.add(edge.dst)
        else:
            payload = ev["payload"]
            if not _apply_status(corpus, payload):
                unresolved_ids.add(payload["id"])

    # Raise if any deferred events still couldn't be applied
    if unresolved_ids:
        sorted_ids = sorted(unresolved_ids)
        raise ValueError(f"deferred event targets unknown node(s): {', '.join(sorted_ids)}")

    return corpus
