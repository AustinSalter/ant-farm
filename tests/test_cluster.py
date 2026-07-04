import pytest

from antfarm.cluster import EmbeddingMatcher, cosine, entailment_clusters
from antfarm.events import node_event
from antfarm.reduce import reduce_events
from helpers import make_corpus_node, make_node

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


def test_find_match_uses_bucket_index_and_ignores_other_buckets():
    vectors = {
        "battery storage caps the pace of solar rollout nationwide.": [1.0, 0.0, 0.0],
        "grid storage is the binding constraint on solar buildout.": [0.99, 0.1411, 0.0],
        "storage capacity, not panel cost, now limits solar deployment.": [0.9, 0.4359, 0.0],
        "coal plants retire on a 40-year schedule.": [0.0, 1.0, 0.0],
        "utility interconnection queues now delay most new solar projects.": [1.0, 0.0, 0.0],
    }

    def embed(texts: list[str]) -> list[list[float]]:
        return [vectors[t.lower()] for t in texts]

    query = make_node("Battery storage caps the pace of solar rollout nationwide.")
    best = make_corpus_node("Grid storage is the binding constraint on solar buildout.")
    middle = make_corpus_node("Storage capacity, not panel cost, now limits solar deployment.")
    low = make_corpus_node("Coal plants retire on a 40-year schedule.")
    # Same text/vector as a perfect match, but a different type -> different bucket,
    # and must be ignored even though its cosine (1.0) beats every in-bucket candidate.
    other_bucket = make_corpus_node(
        "Utility interconnection queues now delay most new solar projects.", type="evidence")

    nodes = {n.id: n for n in [best, middle, low, other_bucket]}
    matcher = EmbeddingMatcher(embed, threshold=0.5)
    assert matcher.find_match(query, nodes) == best.id


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
    ("Nuclear power plants take over a decade to build in most Western countries.",
     "In most Western nations, building a nuclear plant takes more than ten years."),
    ("Electric vehicles produce fewer lifetime emissions than gasoline cars.",
     "Over their lifetime, EVs emit less carbon than gas-powered cars."),
]
DISTINCT_PAIRS = [
    ("Home solar panels pay for themselves within ten years in most US states.",
     "Utility-scale solar is cheaper per watt than rooftop solar."),
    ("Remote work reduces total carbon emissions from commuting.",
     "Remote work increases residential energy consumption."),
    ("Nuclear power plants take over a decade to build in most Western countries.",
     "Nuclear power plants produce zero operational carbon emissions."),
    ("Electric vehicles produce fewer lifetime emissions than gasoline cars.",
     "Electric vehicle battery production requires significant lithium mining."),
]


# Threshold 0.67 decided 2026-07-04 per spec §13.1 from measured cosine similarities
# with chromadb's DefaultEmbeddingFunction:
#   PARAPHRASE pair 1 (solar payback):                        0.6717
#   PARAPHRASE pair 2 (remote work emissions):                0.6771
#   PARAPHRASE pair 3 (nuclear build time):                   0.8242
#   PARAPHRASE pair 4 (EV lifetime emissions):                0.7574
#   DISTINCT pair 1 (rooftop vs utility-scale):               0.4817
#   DISTINCT pair 2 (remote work emissions vs resid. energy): 0.6650
#   DISTINCT pair 3 (nuclear build vs zero-carbon claim):     0.3777
#   DISTINCT pair 4 (EV emissions vs battery mining):         0.4614
# Note: the margin over the hardest distinct pair (0.6650, pair 2) is thin; pairs
# 3 and 4 (added 2026-07-04) separate with more headroom on both sides.
@pytest.mark.eval
def test_merge_fidelity_with_real_embeddings():
    """Spec §10.3: paraphrases must merge; genuine variants must separate."""
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    def embed(texts: list[str]) -> list[list[float]]:
        ef = DefaultEmbeddingFunction()
        return [list(map(float, v)) for v in ef(texts)]

    for a, b in PARAPHRASE_PAIRS:
        assert len(entailment_clusters([a, b], embed, threshold=0.67)) == 1, (a, b)
    for a, b in DISTINCT_PAIRS:
        assert len(entailment_clusters([a, b], embed, threshold=0.67)) == 2, (a, b)
