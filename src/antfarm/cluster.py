import hashlib
import json
import math
from collections.abc import Callable
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from antfarm.reduce import CorpusNode
from antfarm.schema import Node

EmbedFn = Callable[[list[str]], list[list[float]]]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _normalize(vec: list[float]) -> NDArray[np.float64]:
    arr = np.asarray(vec, dtype=np.float64)
    norm = np.linalg.norm(arr)
    return arr / norm if norm else arr


class _Bucket:
    """Normalized candidate vectors for one (type, question_id) bucket."""

    __slots__ = ("ids", "matrix")

    def __init__(self) -> None:
        self.ids: list[str] = []
        self.matrix: NDArray[np.float64] | None = None

    def rebuild(self, candidates: list[tuple[str, list[float]]]) -> None:
        self.ids = [cid for cid, _ in candidates]
        self.matrix = (np.vstack([_normalize(v) for _, v in candidates])
                       if candidates else None)

    def append(self, candidates: list[tuple[str, list[float]]]) -> None:
        if not candidates:
            return
        new_rows = np.vstack([_normalize(v) for _, v in candidates])
        self.ids.extend(cid for cid, _ in candidates)
        self.matrix = new_rows if self.matrix is None else np.vstack([self.matrix, new_rows])

    def best_match(self, query: NDArray[np.float64]) -> tuple[str | None, float]:
        if self.matrix is None or not self.ids:
            return None, 0.0
        scores = self.matrix @ query
        idx = int(np.argmax(scores))
        return self.ids[idx], float(scores[idx])


class EmbeddingMatcher:
    def __init__(self, embed_fn: EmbedFn, threshold: float = 0.67):
        self.embed_fn = embed_fn
        self.threshold = threshold
        self._cache: dict[str, list[float]] = {}
        self._buckets: dict[tuple[str, str], _Bucket] = {}

    def _vec(self, text: str) -> list[float]:
        if text not in self._cache:
            self._cache[text] = self.embed_fn([text])[0]
        return self._cache[text]

    def _sync_bucket(self, key: tuple[str, str], nodes: dict[str, CorpusNode]) -> _Bucket:
        candidate_ids = [cid for cid, c in nodes.items()
                         if c.type == key[0] and c.question_id == key[1]]
        bucket = self._buckets.setdefault(key, _Bucket())
        indexed = set(bucket.ids)
        current = set(candidate_ids)
        # nodes are only ever added by the reducer, never removed mid-fold; if a
        # previously-indexed id is missing from `nodes`, rebuild defensively.
        if not indexed.issubset(current):
            bucket.rebuild([(cid, self._vec(nodes[cid].text)) for cid in candidate_ids])
            return bucket
        missing = [cid for cid in candidate_ids if cid not in indexed]
        if missing:
            bucket.append([(cid, self._vec(nodes[cid].text)) for cid in missing])
        return bucket

    def find_match(self, node: Node, nodes: dict[str, CorpusNode]) -> str | None:
        query = _normalize(self._vec(node.text))
        bucket = self._sync_bucket((node.type, node.question_id), nodes)
        best_id, best_score = bucket.best_match(query)
        return best_id if best_score >= self.threshold else None


def entailment_clusters(texts: list[str], embed_fn: EmbedFn,
                        threshold: float = 0.67) -> list[list[int]]:
    vecs = embed_fn(texts)
    clusters: list[list[int]] = []
    for i, vec in enumerate(vecs):
        for cluster in clusters:
            if any(cosine(vec, vecs[j]) >= threshold for j in cluster):
                cluster.append(i)
                break
        else:
            clusters.append([i])
    return clusters


def hash_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic 256-dim hashed word unigram+bigram embedding. For tests and
    offline smoke runs (ANTFARM_EMBED=hash) - not a semantic model. Word grams in
    256 dims keep distinct sentences well below the 0.67 entailment threshold
    (char trigrams did not: nearly all English pairs merged)."""
    out = []
    for text in texts:
        vec = [0.0] * 256
        words = text.lower().split()
        grams = words + [f"{a} {b}" for a, b in zip(words, words[1:], strict=False)]
        for gram in grams:
            digest = hashlib.sha256(gram.encode()).digest()
            vec[int.from_bytes(digest[:2], "big") % 256] += 1.0
        out.append(vec)
    return out


class CachedEmbed:
    """File-backed embedding cache keyed by text hash, so repeated CLI
    invocations (gate, probe, materialize) don't re-embed the whole corpus."""

    def __init__(self, path: Path, base: EmbedFn):
        self.path = path
        self.base = base
        self._cache: dict[str, list[float]] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {})

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:24]

    def __call__(self, texts: list[str]) -> list[list[float]]:
        missing = [t for t in texts if self._key(t) not in self._cache]
        if missing:
            for text, vec in zip(missing, self.base(missing), strict=True):
                self._cache[self._key(text)] = vec
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._cache), encoding="utf-8")
        return [self._cache[self._key(t)] for t in texts]
