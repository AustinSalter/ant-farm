from antfarm.analysis import ach_winner, derive_e
from antfarm.reduce import Corpus
from helpers import make_corpus_node, make_edge


def _ach_corpus():
    h1 = make_corpus_node("Storage constraints bind solar growth.", type="hypothesis")
    h2 = make_corpus_node("No single constraint binds solar growth.", type="hypothesis")
    e1 = make_corpus_node("California curtailed 2.4 TWh of solar in 2024.",
                          type="evidence")
    e2 = make_corpus_node("Battery installs rose 40% in 2024.", type="evidence")
    corpus = Corpus(nodes={n.id: n for n in (h1, h2, e1, e2)}, edges=[
        # e1 cuts against h2 only; e2 is consistent with everything (non-diagnostic)
        make_edge(e1.id, h1.id, "scored_against", consistency="consistent"),
        make_edge(e1.id, h2.id, "scored_against", consistency="inconsistent"),
        make_edge(e2.id, h1.id, "scored_against", consistency="consistent"),
        make_edge(e2.id, h2.id, "scored_against", consistency="consistent"),
    ])
    return corpus, h1.id, h2.id, e2.id


def test_winner_by_least_inconsistency_discarding_nondiagnostic():
    corpus, h1_id, h2_id, e2_id = _ach_corpus()
    result = ach_winner(corpus, "q-1")
    assert result["winner"] == h1_id
    assert result["inconsistency"][h2_id] == 1
    assert result["discarded_nondiagnostic"] == [e2_id]


def test_tie_yields_no_winner():
    corpus, h1_id, h2_id, _ = _ach_corpus()
    corpus.edges = []  # no diagnostic evidence at all
    result = ach_winner(corpus, "q-1")
    assert result["winner"] is None
    assert sorted(result["tied"]) == sorted([h1_id, h2_id])


def test_ach_scoring_is_question_scoped():
    corpus, h1_id, h2_id, e2_id = _ach_corpus()
    other_q = make_corpus_node("An unrelated hypothesis for a different question.",
                               type="hypothesis")
    other_q = other_q.model_copy(update={"question_id": "q-other"})
    corpus.nodes[other_q.id] = other_q
    e1_id = next(e.src for e in corpus.edges if e.consistency == "inconsistent")
    corpus.edges.append(make_edge(e1_id, other_q.id, "scored_against",
                                  consistency="consistent"))
    # evidence scored against one q-1 hypothesis and one q-other hypothesis:
    # the cross-question cell must not make it look non-diagnostic for q-1
    e3 = make_corpus_node("Texas added record utility-scale storage in 2025.",
                          type="evidence")
    corpus.nodes[e3.id] = e3
    corpus.edges.append(make_edge(e3.id, h1_id, "scored_against",
                                  consistency="consistent"))
    corpus.edges.append(make_edge(e3.id, other_q.id, "scored_against",
                                  consistency="consistent"))
    result = ach_winner(corpus, "q-1")
    assert e1_id not in result["discarded_nondiagnostic"]
    assert result["discarded_nondiagnostic"] == [e2_id]
    assert result["winner"] == h1_id


def test_derive_e_counts_live_verified_high_diagnostic_evidence():
    corpus = Corpus()
    assert derive_e(corpus, "q-1") == "low"
    texts = [f"Distinct verified diagnostic fact number {i} about storage." for i in range(5)]
    for i, text in enumerate(texts):
        node = make_corpus_node(text, type="evidence", verified=True,
                                diagnosticity="high")
        corpus.nodes[node.id] = node
        if i == 1:
            assert derive_e(corpus, "q-1") == "med"  # 2 -> med
    assert derive_e(corpus, "q-1") == "high"  # 5 -> high
