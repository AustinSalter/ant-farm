from typing import Any, Literal, Protocol, get_args

from pydantic import BaseModel, Field

from antfarm.schema import Edge, Node, NodeStatus, Vantage

_DIAG_RANK = {None: 0, "none": 1, "med": 2, "high": 3}
_VALID_STATUSES = set(get_args(NodeStatus))


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


def _apply_status(corpus: Corpus, payload: dict[str, Any]) -> bool:
    status = payload["status"]
    if status not in _VALID_STATUSES:
        valid = ", ".join(sorted(_VALID_STATUSES))
        raise ValueError(f"unknown status {status!r}; must be one of: {valid}")
    target = corpus.nodes.get(payload["id"])
    if target is None:
        return False
    target.status = status
    if status in ("conceded", "superseded"):
        target.died_because = payload.get("died_because") or target.died_because
    else:
        target.died_because = None
    return True


def _resolve_edge(edge: Edge, alias: dict[str, str]) -> Edge:
    src, dst = alias.get(edge.src, edge.src), alias.get(edge.dst, edge.dst)
    if src == edge.src and dst == edge.dst:
        return edge
    return edge.model_copy(update={"src": src, "dst": dst})


def _resolve_status_id(payload: dict[str, Any], alias: dict[str, str]) -> dict[str, Any]:
    resolved_id = alias.get(payload["id"], payload["id"])
    if resolved_id == payload["id"]:
        return payload
    return {**payload, "id": resolved_id}


# supersedes/status events whose target node hasn't been seen yet, kept as the
# parsed objects they already are (no re-validation round-trip) and resolved
# once, in the post-fold canonicalization phase.
DeferredEvent = tuple[Literal["edge"], Edge] | tuple[Literal["status"], dict[str, Any]]


def reduce_events(events: list[dict], matcher: Matcher | None = None) -> Corpus:
    corpus = Corpus()
    # merged_id -> canonical_id, populated whenever an incoming node is folded into
    # an existing one (matcher merge or matcher-free re-observation with a different
    # id would be impossible, so this only ever fires for matcher merges)
    alias: dict[str, str] = {}
    deferred: list[DeferredEvent] = []
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
            edge = Edge.model_validate(payload)
            corpus.edges.append(edge)
            resolved = _resolve_edge(edge, alias)
            if edge.rel == "supersedes" and not _apply_supersede(corpus, resolved):
                deferred.append(("edge", edge))
        elif kind == "status":
            if not _apply_status(corpus, _resolve_status_id(payload, alias)):
                deferred.append(("status", payload))
        else:
            raise ValueError(f"unknown event kind: {kind!r}")

    # Canonicalization phase - the one place ids get resolved after the fold:
    # 1. replay deferred events through the now-complete alias map, raising if a
    #    target genuinely never showed up.
    # 2. re-resolve every stored edge and every node's superseded_by pointer,
    #    since either can have been set from an id that only later turned out to
    #    be an alias for something else.
    unresolved_ids: set[str] = set()
    for kind, item in deferred:
        if kind == "edge" and isinstance(item, Edge):
            resolved_edge = _resolve_edge(item, alias)
            if not _apply_supersede(corpus, resolved_edge):
                unresolved_ids.add(resolved_edge.dst)
        elif kind == "status" and isinstance(item, dict):
            resolved_payload = _resolve_status_id(item, alias)
            if not _apply_status(corpus, resolved_payload):
                unresolved_ids.add(resolved_payload["id"])

    if unresolved_ids:
        sorted_ids = sorted(unresolved_ids)
        raise ValueError(f"deferred event targets unknown node(s): {', '.join(sorted_ids)}")

    if alias:
        corpus.edges = [_resolve_edge(e, alias) for e in corpus.edges]
        for corpus_node in corpus.nodes.values():
            if corpus_node.superseded_by is not None:
                corpus_node.superseded_by = alias.get(
                    corpus_node.superseded_by, corpus_node.superseded_by)

    return corpus
