from antfarm.graph import (
    blast_radius,
    build_graph,
    compute_centrality,
    extract_cruxes,
    find_unsublated_undercutters,
)
from antfarm.reduce import Corpus
from helpers import make_corpus_node, make_edge


def _corpus():
    a = make_corpus_node("Solar deployment doubles every three years.")
    b = make_corpus_node("Grid storage capacity limits solar deployment growth.",
                         status="contested")
    c = make_corpus_node("Battery costs fall 15% per doubling of production.")
    d = make_corpus_node("Deployment statistics conflate contracted and installed capacity.")
    f = make_corpus_node("Permitting queues are a second-order constraint on solar buildout.",
                         status="contested")
    corpus = Corpus(nodes={n.id: n for n in (a, b, c, d, f)}, edges=[
        make_edge(a.id, b.id, "depends_on"),
        make_edge(b.id, c.id, "depends_on"),
        make_edge(d.id, a.id, "undercuts"),
    ])
    return corpus, a.id, b.id, c.id, d.id, f.id


def test_build_graph_has_all_nodes_and_edges():
    corpus, *_ = _corpus()
    g = build_graph(corpus)
    assert g.number_of_nodes() == 5 and g.number_of_edges() == 3


def test_blast_radius_walks_depends_on_upstream():
    corpus, a_id, b_id, c_id, d_id, f_id = _corpus()
    g = build_graph(corpus)
    # c fires -> b depends on c, a depends on b: both affected; d does not depend on c
    assert blast_radius(g, c_id) == {a_id, b_id}
    assert blast_radius(g, a_id) == set()


def test_extract_cruxes_ranks_contested_by_centrality():
    corpus, a_id, b_id, c_id, d_id, f_id = _corpus()
    cent = compute_centrality(build_graph(corpus))
    # both b and f are contested; b sits on the dependency chain (high betweenness),
    # f is isolated (zero) - the ranking, not just membership, is under test
    assert extract_cruxes(corpus, cent) == [b_id, f_id]


def test_find_unsublated_undercutters_found_and_cleared():
    corpus, a_id, b_id, c_id, d_id, f_id = _corpus()
    assert find_unsublated_undercutters(corpus) == [(d_id, a_id)]
    # a rebuttal against the undercutter clears it
    corpus.edges.append(make_edge(a_id, d_id, "rebuts"))
    assert find_unsublated_undercutters(corpus) == []
