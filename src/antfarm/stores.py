from pathlib import Path

import chromadb

from antfarm.cluster import EmbedFn
from antfarm.reduce import Corpus, CorpusNode


def _metadata(node: CorpusNode) -> dict:
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
                    embeddings=self.embed_fn(texts),
                    metadatas=[_metadata(corpus.nodes[nid]) for nid in ids],
                )

    def query(self, collection: str, text: str, n: int = 8,
              where: dict | None = None) -> list[dict]:
        col = self.client.get_collection(collection, embedding_function=None)
        res = col.query(query_embeddings=[self.embed_fn([text])[0]],
                        n_results=n, where=where)
        return [
            {"id": i, "text": doc, "metadata": meta, "distance": dist}
            for i, doc, meta, dist in zip(
                res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0],
                strict=False)
        ]
