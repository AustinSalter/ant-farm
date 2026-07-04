from pathlib import Path
from typing import cast

import chromadb
from chromadb.api.types import PyEmbeddings

from antfarm.cluster import EmbedFn
from antfarm.reduce import Corpus, CorpusNode


def _metadata(node: CorpusNode) -> dict:
    # Single-value keys (farm/family/persona/round/sensor) reflect only the
    # originating vantage. Boolean keys (farm_*/family_*/persona_*) are set
    # for every vantage the atom has been sighted from (node.vantages, deduped
    # via dict keys), so they cover any sighting, not just the originating
    # one. Chroma metadata cannot hold list values, and has no substring
    # operator, so these are one-boolean-per-member rather than a CSV blob -
    # each is safe for an exact-match `where` filter, e.g. {"family_gpt": True}.
    vantage_flags = {}
    for v in node.vantages:
        vantage_flags[f"family_{v.family}"] = True
        vantage_flags[f"farm_{v.farm}"] = True
        vantage_flags[f"persona_{v.persona}"] = True
    return {
        "type": node.type,
        "status": node.status,
        "verified": node.verified,
        "sightings": node.sightings,
        "question_id": node.question_id,
        "farm": node.vantage.farm,
        "family": node.vantage.family,
        "persona": node.vantage.persona,
        "round": node.vantage.round,
        "sensor": node.vantage.sensor,
        **vantage_flags,
        "n_vantages": len(node.vantages),
    }


class CorpusStore:
    def __init__(self, client: chromadb.ClientAPI, embed_fn: EmbedFn):
        self.client = client
        self.embed_fn = embed_fn

    @classmethod
    def persistent(cls, persist_dir: Path, embed_fn: EmbedFn) -> "CorpusStore":
        return cls(chromadb.PersistentClient(path=str(persist_dir)), embed_fn=embed_fn)

    def _fresh_collection(self, name: str) -> chromadb.Collection:
        # list_collections returns Collection objects or names depending on version
        existing = {getattr(c, "name", c) for c in self.client.list_collections()}
        if name in existing:
            self.client.delete_collection(name)
        # embedding_function=None: omitting it silently attaches chroma's default
        # ONNX EmbeddingFunction; embeddings are always passed explicitly here.
        return self.client.create_collection(name, embedding_function=None)

    def rebuild(self, corpus: Corpus, view_ids: set[str]) -> None:
        for name, ids in (("well", list(corpus.nodes)), ("view", list(view_ids))):
            collection = self._fresh_collection(name)
            if ids:
                texts = [corpus.nodes[nid].text for nid in ids]
                collection.add(
                    ids=ids,
                    documents=texts,
                    # chroma's typed API wants its own numpy-aware embedding alias;
                    # a plain list[list[float]] is what we actually pass at runtime.
                    embeddings=cast(PyEmbeddings, self.embed_fn(texts)),
                    metadatas=[_metadata(corpus.nodes[nid]) for nid in ids],
                )

    def query(self, collection: str, text: str, n: int = 8,
              where: dict | None = None) -> list[dict]:
        col = self.client.get_collection(collection, embedding_function=None)
        res = col.query(query_embeddings=cast(PyEmbeddings, [self.embed_fn([text])[0]]),
                        n_results=n, where=where)
        # documents/metadatas/distances are typed Optional because `include` is
        # configurable, but we never omit them, so they are always populated here.
        documents, metadatas, distances = res["documents"], res["metadatas"], res["distances"]
        assert documents is not None
        assert metadatas is not None
        assert distances is not None
        return [
            {"id": i, "text": doc, "metadata": meta, "distance": dist}
            for i, doc, meta, dist in zip(
                res["ids"][0], documents[0], metadatas[0], distances[0],
                strict=False)
        ]
