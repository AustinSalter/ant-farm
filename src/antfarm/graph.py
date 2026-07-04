from typing import cast

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


def compute_centrality(g: nx.MultiDiGraph) -> dict[str, float]:
    # networkx ships no inline types; ignore_missing_imports makes its API return Any.
    return cast("dict[str, float]", nx.betweenness_centrality(nx.Graph(g)))


def extract_cruxes(corpus: Corpus, cent: dict[str, float], top_k: int = 5) -> list[str]:
    contested = [nid for nid, node in corpus.nodes.items()
                 if node.status == "contested" or node.type in ("crux", "tension")]
    contested.sort(key=lambda nid: cent.get(nid, 0.0), reverse=True)
    return contested[:top_k]


def answered_challengers(corpus: Corpus) -> set[str]:
    """Challengers that have themselves been rebutted, superseded, or qualified.

    An answer only counts if the answering node (the edge's src) is present in
    the corpus and still live; a rebuttal from a superseded or conceded node
    does not clear the challenge.
    """
    out = set()
    for edge in corpus.edges:
        if edge.rel not in ("rebuts", "supersedes", "qualifies"):
            continue
        answerer = corpus.nodes.get(edge.src)
        if answerer is not None and answerer.status == "live":
            out.add(edge.dst)
    return out


def find_unsublated_undercutters(corpus: Corpus) -> list[tuple[str, str]]:
    answered = answered_challengers(corpus)
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
    return cast("set[str]", nx.ancestors(dep, node_id))


def compute_view(corpus: Corpus, cent: dict[str, float],
                 centrality_floor: float = 0.0) -> set[str]:
    return {
        nid for nid, node in corpus.nodes.items()
        if node.status == "live"
        and node.verified
        and node.diagnosticity != "none"
        and cent.get(nid, 0.0) >= centrality_floor
    }
