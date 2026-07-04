from typing import Protocol

from pydantic import BaseModel, Field

from antfarm.schema import Edge, Node, Vantage

_DIAG_RANK = {None: 0, "none": 1, "med": 2, "high": 3}


class CorpusNode(Node):
    vantages: list[Vantage] = Field(default_factory=list)
    died_because: str | None = None


class Corpus(BaseModel):
    nodes: dict[str, CorpusNode] = Field(default_factory=dict)
    edges: list[Edge] = Field(default_factory=list)


class Matcher(Protocol):
    """Structural interface for entity-resolution matchers.

    Anything with this method (e.g. antfarm.cluster.EmbeddingMatcher) satisfies
    this protocol; reduce.py never imports cluster.py to avoid a circular import.
    """

    def find_match(self, node: Node, nodes: dict[str, CorpusNode]) -> str | None: ...


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


def _resolve_edge(edge: Edge, alias: dict[str, str]) -> Edge:
    src, dst = alias.get(edge.src, edge.src), alias.get(edge.dst, edge.dst)
    if src == edge.src and dst == edge.dst:
        return edge
    return edge.model_copy(update={"src": src, "dst": dst})


def reduce_events(events: list[dict], matcher: Matcher | None = None) -> Corpus:
    corpus = Corpus()
    # merged_id -> canonical_id, populated whenever an incoming node is folded into
    # an existing one (matcher merge or matcher-free re-observation with a different
    # id would be impossible, so this only ever fires for matcher merges)
    alias: dict[str, str] = {}
    deferred: list[dict] = []  # supersedes/status whose target node hasn't been seen yet
    for ev in events:
        kind, payload = ev["kind"], ev["payload"]
        if kind == "node":
            node = Node.model_validate(payload)
            target = node.id if node.id in corpus.nodes else (
                matcher.find_match(node, corpus.nodes) if matcher else None)
            if target:
                _observe(corpus.nodes[target], node)
                if node.id != target:
                    alias[node.id] = target
            else:
                corpus.nodes[node.id] = CorpusNode.model_validate(
                    {**node.model_dump(), "vantages": [node.vantage.model_dump()]})
        elif kind == "edge":
            edge = _resolve_edge(Edge.model_validate(payload), alias)
            corpus.edges.append(edge)
            if edge.rel == "supersedes" and not _apply_supersede(corpus, edge):
                deferred.append({"kind": "edge", "payload": edge.model_dump()})
        elif kind == "status":
            resolved = {**payload, "id": alias.get(payload["id"], payload["id"])}
            if not _apply_status(corpus, resolved):
                deferred.append({"kind": "status", "payload": resolved})
        else:
            raise ValueError(f"unknown event kind: {kind!r}")

    # Re-apply deferred events - resolving through the alias map again, since a
    # merge establishing an alias may itself have arrived after the deferred event -
    # and track failures.
    unresolved_ids: set[str] = set()
    for ev in deferred:
        if ev["kind"] == "edge":
            edge = _resolve_edge(Edge.model_validate(ev["payload"]), alias)
            if not _apply_supersede(corpus, edge):
                unresolved_ids.add(edge.dst)
        else:
            payload = ev["payload"]
            resolved_id = alias.get(payload["id"], payload["id"])
            payload = {**payload, "id": resolved_id}
            if not _apply_status(corpus, payload):
                unresolved_ids.add(resolved_id)

    # Raise if any deferred events still couldn't be applied
    if unresolved_ids:
        sorted_ids = sorted(unresolved_ids)
        raise ValueError(f"deferred event targets unknown node(s): {', '.join(sorted_ids)}")

    # Edges were alias-resolved at append time, but a plain edge can arrive before
    # the node event that establishes its alias. Now that the fold is complete and
    # the alias map is final, re-resolve every stored edge (_resolve_edge only
    # rebuilds an Edge when an id actually changes).
    if alias:
        corpus.edges = [_resolve_edge(e, alias) for e in corpus.edges]

    return corpus
