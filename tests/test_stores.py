import hashlib

import chromadb

from antfarm.reduce import Corpus
from antfarm.stores import CorpusStore
from helpers import make_corpus_node, make_vantage


def hash_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic 8-dim embedding from character trigrams - no model download,
    seed-independent (hashlib, not hash())."""
    out = []
    for text in texts:
        vec = [0.0] * 8
        for i in range(len(text) - 2):
            tri = text[i:i + 3].encode()
            vec[int.from_bytes(hashlib.sha256(tri).digest()[:2], "big") % 8] += 1.0
        out.append(vec)
    return out


def _corpus():
    corpus = Corpus()
    for text, verified in [
        ("Grid storage capacity limits solar deployment growth.", True),
        ("Battery costs fall 15% per doubling of production.", False),
    ]:
        n = make_corpus_node(text, verified=verified)
        corpus.nodes[n.id] = n
    return corpus


def _store():
    return CorpusStore(chromadb.EphemeralClient(), embed_fn=hash_embed)


def test_routing_well_gets_everything_view_gets_subset():
    corpus = _corpus()
    view_ids = {nid for nid, n in corpus.nodes.items() if n.verified}
    store = _store()
    store.rebuild(corpus, view_ids)
    assert len(store.query("well", "solar", n=10)) == 2
    assert {h["id"] for h in store.query("view", "solar", n=10)} == view_ids


def test_metadata_filters():
    corpus = _corpus()
    store = _store()
    store.rebuild(corpus, set(corpus.nodes))
    hits = store.query("well", "solar", n=10, where={"verified": True})
    assert len(hits) == 1 and hits[0]["metadata"]["family"] == "claude"


def test_rebuild_is_idempotent():
    corpus = _corpus()
    store = _store()
    store.rebuild(corpus, set())
    store.rebuild(corpus, set())  # must not raise or duplicate
    assert len(store.query("well", "solar", n=10)) == 2


def test_metadata_boolean_keys_cover_every_sighting_vantage():
    corpus = Corpus()
    n = make_corpus_node("Grid storage capacity limits solar deployment growth.",
                         verified=True)
    n.vantages.append(make_vantage(farm="B", family="gpt", persona="skeptic"))
    corpus.nodes[n.id] = n
    store = _store()
    store.rebuild(corpus, set(corpus.nodes))
    hits = store.query("well", "solar", n=10)
    meta = hits[0]["metadata"]
    assert meta["family_claude"] is True
    assert meta["family_gpt"] is True
    assert meta["farm_A"] is True
    assert meta["farm_B"] is True
    assert meta["persona_analyst"] is True
    assert meta["persona_skeptic"] is True
    assert meta["n_vantages"] == 2
    # single-value keys still reflect the originating vantage
    assert meta["family"] == "claude"
    # the footgun the CSV design couldn't satisfy: an exact-match where
    # filter on a non-originating vantage member must still find the node
    filtered = store.query("well", "solar", n=10, where={"family_gpt": True})
    assert {h["id"] for h in filtered} == {n.id}
