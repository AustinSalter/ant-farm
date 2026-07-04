import pytest

from antfarm.cluster import EmbeddingMatcher, cosine, entailment_clusters
from antfarm.events import node_event
from antfarm.reduce import reduce_events
from helpers import make_node

# Deterministic fake: identical vector for texts sharing a canned key, orthogonal otherwise.
_CANNED = {
    "grid storage is the binding constraint on solar buildout.": [1.0, 0.0, 0.0],
    "storage capacity, not panel cost, now limits solar deployment.": [0.96, 0.28, 0.0],
    "coal plants retire on a 40-year schedule.": [0.0, 1.0, 0.0],
}


def fake_embed(texts: list[str]) -> list[list[float]]:
    return [_CANNED[t.lower()] for t in texts]


def test_cosine():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_paraphrase_merges_as_observation():
    a = make_node("Grid storage is the binding constraint on solar buildout.")
    b = make_node("Storage capacity, not panel cost, now limits solar deployment.")
    matcher = EmbeddingMatcher(fake_embed, threshold=0.85)
    corpus = reduce_events([node_event(a), node_event(b)], matcher=matcher)
    assert len(corpus.nodes) == 1
    assert corpus.nodes[a.id].sightings == 2


def test_distinct_claim_does_not_merge():
    a = make_node("Grid storage is the binding constraint on solar buildout.")
    b = make_node("Coal plants retire on a 40-year schedule.")
    matcher = EmbeddingMatcher(fake_embed, threshold=0.85)
    corpus = reduce_events([node_event(a), node_event(b)], matcher=matcher)
    assert len(corpus.nodes) == 2


def test_never_matches_across_types():
    a = make_node("Grid storage is the binding constraint on solar buildout.")
    b = make_node("Storage capacity, not panel cost, now limits solar deployment.",
                  type="evidence")
    matcher = EmbeddingMatcher(fake_embed, threshold=0.85)
    corpus = reduce_events([node_event(a), node_event(b)], matcher=matcher)
    assert len(corpus.nodes) == 2


def test_entailment_clusters_groups_paraphrases():
    texts = ["Grid storage is the binding constraint on solar buildout.",
             "Storage capacity, not panel cost, now limits solar deployment.",
             "Coal plants retire on a 40-year schedule."]
    clusters = entailment_clusters(texts, fake_embed, threshold=0.85)
    assert sorted(map(sorted, clusters)) == [[0, 1], [2]]


PARAPHRASE_PAIRS = [
    ("Home solar panels pay for themselves within ten years in most US states.",
     "In the majority of US states, rooftop solar recoups its cost in under a decade."),
    ("Remote work reduces total carbon emissions from commuting.",
     "Commuting emissions fall when employees work from home."),
]
DISTINCT_PAIRS = [
    ("Home solar panels pay for themselves within ten years in most US states.",
     "Utility-scale solar is cheaper per watt than rooftop solar."),
    ("Remote work reduces total carbon emissions from commuting.",
     "Remote work increases residential energy consumption."),
]


@pytest.mark.eval
def test_merge_fidelity_with_real_embeddings():
    """Spec §10.3: paraphrases must merge; genuine variants must separate."""
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    def embed(texts: list[str]) -> list[list[float]]:
        ef = DefaultEmbeddingFunction()
        return [list(map(float, v)) for v in ef(texts)]

    for a, b in PARAPHRASE_PAIRS:
        assert len(entailment_clusters([a, b], embed, threshold=0.85)) == 1, (a, b)
    for a, b in DISTINCT_PAIRS:
        assert len(entailment_clusters([a, b], embed, threshold=0.85)) == 2, (a, b)
