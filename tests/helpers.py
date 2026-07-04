"""Shared test builders. Import these; never re-declare them in a test file."""

from antfarm.reduce import CorpusNode
from antfarm.schema import Edge, Node, Vantage, atom_id


def make_vantage(**overrides) -> Vantage:
    defaults = {"run": "r1", "farm": "A", "family": "claude", "persona": "analyst",
                "round": 1, "sensor": "model"}
    return Vantage(**{**defaults, **overrides})


V = make_vantage()


def make_node(text: str, *, type: str = "claim", vantage: Vantage = V, **kwargs) -> Node:
    return Node.create(type=type, text=text, vantage=vantage,
                       question_id="q-1", ts="2026-07-03T00:00:00Z", **kwargs)


def make_corpus_node(text: str, *, type: str = "claim", **kwargs) -> CorpusNode:
    nid = atom_id(type, text)
    return CorpusNode(id=nid, type=type, text=text, vantage=V, vantages=[V],
                      question_id="q-1", ts="t", **kwargs)


def make_edge(src: str, dst: str, rel: str, **kwargs) -> Edge:
    return Edge(src=src, dst=dst, rel=rel, vantage=V, ts="t", **kwargs)
