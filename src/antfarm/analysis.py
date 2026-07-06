"""Phase 5/7 computed judgments: ACH winner by least inconsistency with
non-diagnostic evidence discarded (Heuer, spec §5 Phase 5), and the derived
E band (spec §7 - diagnosticity counts now, rarefaction slope in plan 3)."""

from collections import defaultdict

from antfarm.emission import Band
from antfarm.reduce import Corpus


def ach_scores(corpus: Corpus, question_id: str) -> dict:
    hypotheses = {nid for nid, n in corpus.nodes.items()
                  if n.type == "hypothesis" and n.question_id == question_id}
    cells: dict[str, dict[str, str]] = defaultdict(dict)
    for edge in corpus.edges:
        if edge.rel != "scored_against" or edge.consistency is None:
            continue
        if edge.dst not in hypotheses:
            continue
        cells[edge.src][edge.dst] = edge.consistency
    discarded = sorted(ev for ev, row in cells.items()
                       if len(row) >= 2 and "inconsistent" not in row.values())
    inconsistency = dict.fromkeys(sorted(hypotheses), 0)
    for ev, row in cells.items():
        if ev in discarded:
            continue
        for hyp, consistency in row.items():
            if consistency == "inconsistent":
                inconsistency[hyp] += 1
    return {"inconsistency": inconsistency, "discarded_nondiagnostic": discarded}


def ach_winner(corpus: Corpus, question_id: str) -> dict:
    scores = ach_scores(corpus, question_id)
    live = [nid for nid, n in corpus.nodes.items()
            if n.type == "hypothesis" and n.question_id == question_id
            and n.status in ("live", "contested")]
    counts = {nid: scores["inconsistency"].get(nid, 0) for nid in live}
    if not counts:
        return {"winner": None, "tied": [], **scores}
    best = min(counts.values())
    winners = sorted(nid for nid, c in counts.items() if c == best)
    if len(winners) == 1:
        return {"winner": winners[0], "tied": [], **scores}
    return {"winner": None, "tied": winners, **scores}


def derive_e(corpus: Corpus, question_id: str) -> Band:
    count = sum(
        1 for node in corpus.nodes.values()
        if node.type == "evidence" and node.question_id == question_id
        and node.status == "live" and node.verified and node.diagnosticity == "high")
    if count < 2:
        return "low"
    if count < 5:
        return "med"
    return "high"
