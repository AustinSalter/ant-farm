import pytest

from antfarm.graph import (
    answered_challengers,
    blast_radius,
    build_graph,
    compute_centrality,
    compute_view,
    extract_cruxes,
    find_unsublated_undercutters,
    is_standing_challenge,
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


def test_extract_cruxes_excludes_superseded_tension():
    live_tension = make_corpus_node("Grid buildout and demand growth are in tension.",
                                     type="tension")
    dead_tension = make_corpus_node("Storage costs and deployment pace are in tension.",
                                     type="tension", status="superseded")
    corpus = Corpus(nodes={n.id: n for n in (live_tension, dead_tension)})
    cent: dict[str, float] = {}
    result = extract_cruxes(corpus, cent)
    assert live_tension.id in result
    assert dead_tension.id not in result


def test_answered_challengers_requires_live_answerer():
    challenger = make_corpus_node("Sensor drift explains the observed anomaly.")
    live_rebuttal = make_corpus_node("Calibration logs rule out sensor drift.")
    dead_rebuttal = make_corpus_node("An early analysis dismissed sensor drift.",
                                     status="superseded")

    # rebutted by a live node -> answered
    corpus = Corpus(
        nodes={n.id: n for n in (challenger, live_rebuttal)},
        edges=[make_edge(live_rebuttal.id, challenger.id, "rebuts")],
    )
    assert answered_challengers(corpus) == {challenger.id}

    # only rebuttal comes from a superseded node -> not answered
    corpus = Corpus(
        nodes={n.id: n for n in (challenger, dead_rebuttal)},
        edges=[make_edge(dead_rebuttal.id, challenger.id, "rebuts")],
    )
    assert answered_challengers(corpus) == set()

    # rebuttal edge whose src is absent from corpus.nodes -> not answered
    corpus = Corpus(
        nodes={challenger.id: challenger},
        edges=[make_edge("missing-node-id", challenger.id, "rebuts")],
    )
    assert answered_challengers(corpus) == set()


GATE_TEXT = "Verified live claims about solar economics enter the view."


@pytest.mark.parametrize("kwargs,admitted", [
    ({"verified": True}, True),
    ({"verified": False}, False),
    ({"verified": True, "status": "contested"}, False),
    ({"verified": True, "status": "superseded"}, False),
])
def test_view_gate_admission(kwargs, admitted):
    n = make_corpus_node(GATE_TEXT, **kwargs)
    corpus = Corpus(nodes={n.id: n})
    assert (n.id in compute_view(corpus, cent={})) is admitted


def test_view_gate_excludes_non_diagnostic_evidence():
    n = make_corpus_node("Both hypotheses predict rising battery production.",
                         type="evidence", verified=True, diagnosticity="none")
    corpus = Corpus(nodes={n.id: n})
    assert compute_view(corpus, cent={}) == set()


def test_view_gate_centrality_floor():
    n = make_corpus_node(GATE_TEXT, verified=True)
    corpus = Corpus(nodes={n.id: n})
    assert compute_view(corpus, cent={n.id: 0.1}, centrality_floor=0.2) == set()
    assert compute_view(corpus, cent={n.id: 0.3}, centrality_floor=0.2) == {n.id}


def test_is_standing_challenge():
    live_challenger = make_corpus_node("Sensor drift explains the observed anomaly.")
    dead_challenger = make_corpus_node("An early theory blamed calibration error.",
                                       status="superseded")
    target = make_corpus_node("The anomaly reflects a genuine signal.")
    corpus = Corpus(nodes={n.id: n for n in (live_challenger, dead_challenger, target)})

    live_edge = make_edge(live_challenger.id, target.id, "rebuts")
    dead_edge = make_edge(dead_challenger.id, target.id, "rebuts")
    missing_edge = make_edge("missing-node-id", target.id, "rebuts")

    assert is_standing_challenge(live_edge, corpus, answered=set()) is True
    # challenger is not live -> not standing
    assert is_standing_challenge(dead_edge, corpus, answered=set()) is False
    # challenger absent from corpus -> not standing
    assert is_standing_challenge(missing_edge, corpus, answered=set()) is False
    # challenger has been answered -> not standing
    assert is_standing_challenge(live_edge, corpus, answered={live_challenger.id}) is False
