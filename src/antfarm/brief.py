"""Computed briefs: warm start (Phase 1), stitch input (Phase 5), the
verification queue (Phase 4 floor), and the hole probe (Phase 6)."""

import json
from pathlib import Path

from antfarm.cluster import EmbedFn, cosine
from antfarm.farm import last_compressed, read_meta, read_outcome
from antfarm.graph import build_graph, compute_centrality, compute_view, extract_cruxes
from antfarm.reduce import Corpus
from antfarm.tripwires import standing_tripwires

_PROBE_TYPES = ("claim", "evidence", "hypothesis", "tension")


def warm_brief(corpus: Corpus, question_id: str, runs_root: Path) -> dict:
    graph = build_graph(corpus)
    cent = compute_centrality(graph)
    view_ids = compute_view(corpus, cent)
    top = sorted(view_ids, key=lambda nid: cent.get(nid, 0.0), reverse=True)[:10]
    cruxes = extract_cruxes(corpus, cent)
    conceded = [{"text": n.text, "died_because": n.died_because}
                for n in corpus.nodes.values()
                if n.type == "hypothesis" and n.status == "conceded"]
    declaration = None
    declarations = sorted(runs_root.glob("*/declaration.json")) if runs_root.exists() else []
    if declarations:
        declaration = json.loads(declarations[-1].read_text(encoding="utf-8"))
    return {
        "question_id": question_id,
        "view": [{"id": nid, "text": corpus.nodes[nid].text} for nid in top],
        "cruxes": [{"id": nid, "text": corpus.nodes[nid].text} for nid in cruxes],
        "conceded": conceded,
        "tripwires": len(standing_tripwires(corpus)),
        "declaration": declaration,
    }


def stitch_brief(corpus: Corpus, corpus_dir: Path, run: str) -> dict:
    farms = []
    farms_root = corpus_dir / "farms" / run
    if farms_root.exists():
        for d in sorted(farms_root.iterdir()):
            if not (d / "meta.json").exists():
                continue
            meta = read_meta(d)
            farms.append({"farm": meta.farm, "hypothesis_id": meta.hypothesis_id,
                          "hypothesis_text": meta.hypothesis_text,
                          "compressed_state": last_compressed(d),
                          "outcome": read_outcome(d)})
    evidence = [{"id": nid, "text": n.text, "strength": n.strength,
                 "diagnosticity": n.diagnosticity, "verified": n.verified}
                for nid, n in sorted(corpus.nodes.items()) if n.type == "evidence"]
    hypotheses = [{"id": nid, "text": n.text, "status": n.status}
                  for nid, n in sorted(corpus.nodes.items()) if n.type == "hypothesis"]
    return {"farms": farms, "evidence": evidence, "hypotheses": hypotheses}


def verification_queue(corpus: Corpus) -> list[dict]:
    out = []
    for nid, node in corpus.nodes.items():
        if (node.type in ("claim", "evidence") and node.status == "live"
                and not node.verified and node.sightings == 1
                and node.vantages and node.vantages[0].sensor == "model"):
            first_round = node.vantages[0].round
            out.append({"id": nid, "text": node.text, "type": node.type,
                        "round": first_round, "late": first_round >= 2})
    return sorted(out, key=lambda item: (-item["round"], item["id"]))


def probe(corpus: Corpus, embed: EmbedFn, text: str, threshold: float = 0.67) -> dict:
    candidates = [(nid, node.text) for nid, node in sorted(corpus.nodes.items())
                  if node.type in _PROBE_TYPES]
    if not candidates:
        return {"novel": True, "nearest": []}
    vectors = embed([text] + [c[1] for c in candidates])
    query, rest = vectors[0], vectors[1:]
    scored = sorted(
        ({"id": nid, "score": cosine(query, vec), "text": ctext}
         for (nid, ctext), vec in zip(candidates, rest, strict=True)),
        key=lambda hit: -hit["score"])  # type: ignore[operator]
    nearest = scored[:3]
    return {"novel": nearest[0]["score"] < threshold, "nearest": nearest}  # type: ignore[operator]
