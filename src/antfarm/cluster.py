import math
from collections.abc import Callable

from antfarm.reduce import CorpusNode
from antfarm.schema import Node

EmbedFn = Callable[[list[str]], list[list[float]]]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class EmbeddingMatcher:
    def __init__(self, embed_fn: EmbedFn, threshold: float = 0.67):
        self.embed_fn = embed_fn
        self.threshold = threshold
        self._cache: dict[str, list[float]] = {}

    def _vec(self, text: str) -> list[float]:
        if text not in self._cache:
            self._cache[text] = self.embed_fn([text])[0]
        return self._cache[text]

    def find_match(self, node: Node, nodes: dict[str, CorpusNode]) -> str | None:
        query = self._vec(node.text)
        best_id, best_score = None, 0.0
        for candidate in nodes.values():
            if candidate.type != node.type or candidate.question_id != node.question_id:
                continue
            score = cosine(query, self._vec(candidate.text))
            if score > best_score:
                best_id, best_score = candidate.id, score
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
