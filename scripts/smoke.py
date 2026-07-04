"""End-to-end smoke test for the antfarm data layer.

Drives the whole pipeline the way plan 2's orchestrator will:
JSONL event log -> reducer with a real embedding matcher -> graph queries ->
computed view gate -> chroma store rebuild + query -> keel transcript export ->
counterfactuals -> obsidian render.

Run: uv run python scripts/smoke.py
Exits non-zero on the first failed check. Downloads the default chroma
embedding model on first run (cached in ~/.cache/chroma afterwards).
"""

import json
import sys
import tempfile
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from antfarm.cluster import EmbeddingMatcher
from antfarm.events import append_events, edge_event, node_event, read_events, status_event
from antfarm.graph import (
    build_graph,
    compute_centrality,
    compute_view,
    extract_cruxes,
    find_unsublated_undercutters,
)
from antfarm.reduce import reduce_events
from antfarm.render import render_obsidian
from antfarm.schema import Edge, Node, Vantage
from antfarm.stores import CorpusStore
from antfarm.transcript import Outcome, Turn, VerificationStats, write_transcript

CHECKS: list[str] = []


def check(name: str, condition: bool) -> None:
    status = "ok" if condition else "FAIL"
    line = f"  [{status}] {name}"
    print(line)
    CHECKS.append(name)
    if not condition:
        sys.exit(f"smoke test failed at: {name}")


def main() -> None:
    ef = DefaultEmbeddingFunction()

    def embed(texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in ef(texts)]

    v_a = Vantage(run="r1", farm="A", family="claude", persona="analyst", round=1, sensor="model")
    v_b = Vantage(run="r1", farm="B", family="gpt", persona="skeptic", round=1, sensor="model")
    ts = "2026-07-04T00:00:00Z"
    q = "q-smoke"

    def node(text: str, vantage: Vantage, **kw) -> Node:
        return Node.create(type=kw.pop("type", "claim"), text=text, vantage=vantage,
                           question_id=q, ts=ts, **kw)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # --- 1. Event log: two farms append, replay order is deterministic ---
        print("event log")
        claim = node("Nuclear power plants take over a decade to build in most Western countries.",
                     v_a, verified=True)
        paraphrase = node(
            "In most Western nations, building a nuclear plant takes more than ten years.",
            v_b, verified=True)
        evidence = node("Vogtle units 3 and 4 took fifteen years from license to operation.",
                        v_a, type="evidence", strength=4, diagnosticity="high", verified=True)
        undercutter = node("Construction-time statistics exclude cancelled reactor projects.", v_b)
        old = node("Reactor construction times are declining industry-wide.", v_a)
        hypothesis = node("Small modular reactors reach grid scale before 2030.", v_b)

        append_events(root / "r0001", "p1-farmA", [
            node_event(claim), node_event(evidence), node_event(old),
            edge_event(Edge(src=evidence.id, dst=claim.id, rel="supports",
                            warrant="a flagship build exceeding a decade evidences the pattern",
                            vantage=v_a, ts=ts)),
        ])
        append_events(root / "r0001", "p2-farmB", [
            node_event(paraphrase),  # entailment-merges into claim
            node_event(undercutter), node_event(hypothesis),
            edge_event(Edge(src=undercutter.id, dst=claim.id, rel="undercuts", vantage=v_b, ts=ts)),
            edge_event(Edge(src=claim.id, dst=old.id, rel="supersedes", vantage=v_b, ts=ts)),
            status_event(hypothesis.id, "conceded", ts=ts,
                         died_because="no deployment evidence by 2026"),
        ])
        events = read_events(root)
        check(f"replayed {len(events)} events from two farm files", len(events) == 10)

        # --- 2. Reducer with real embeddings: paraphrase merges, supersession applies ---
        print("reducer + entailment merge (real embeddings)")
        corpus = reduce_events(events, matcher=EmbeddingMatcher(embed))
        check("paraphrase merged as observation, not duplicate",
              paraphrase.id not in corpus.nodes and corpus.nodes[claim.id].sightings == 2)
        check("merged node carries both vantages",
              {vt.farm for vt in corpus.nodes[claim.id].vantages} == {"A", "B"})
        check("supersession applied without deletion",
              corpus.nodes[old.id].status == "superseded"
              and corpus.nodes[old.id].superseded_by == claim.id
              and old.id in corpus.nodes)
        check("conceded hypothesis keeps died_because",
              corpus.nodes[hypothesis.id].died_because == "no deployment evidence by 2026")

        # --- 3. Graph queries ---
        print("graph queries")
        graph = build_graph(corpus)
        cent = compute_centrality(graph)
        cruxes = extract_cruxes(corpus, cent)
        standing = find_unsublated_undercutters(corpus)
        check("undercutter is standing (live, unanswered)",
              (undercutter.id, claim.id) in standing)
        check("conceded hypothesis is not a crux", hypothesis.id not in cruxes)

        # --- 4. View gate + chroma store ---
        print("view gate + chroma store")
        view_ids = compute_view(corpus, cent)
        check("view admits only live+verified atoms",
              claim.id in view_ids and evidence.id in view_ids
              and undercutter.id not in view_ids and old.id not in view_ids)
        store = CorpusStore(chromadb.EphemeralClient(), embed_fn=embed)
        store.rebuild(corpus, view_ids)
        hits = store.query("view", "how long does it take to build a nuclear reactor", n=3)
        check("semantic query over the view finds the claim",
              any(h["id"] == claim.id for h in hits))
        refound = store.query("well", "nuclear construction duration", n=5,
                              where={"family_gpt": True})
        check("boolean vantage key filters re-found atom by family",
              any(h["id"] == claim.id for h in refound))

        # --- 5. Transcript export + render ---
        print("transcript export + obsidian render")
        turns = [
            Turn(turn=0, role="user", phase=None, iteration=1,
                 content="How long do reactors take to build?"),
            Turn(turn=1, role="assistant", phase="expand", iteration=1,
                 content="Over a decade in the West."),
        ]
        outcome = Outcome(decision="CONCLUDE", ledger_clean=True,
                          verification=VerificationStats(atoms_emitted=6, atoms_verified=3))
        trace_path, stats_path = write_transcript(root / "farmA", turns, v_a, outcome)
        lines = [json.loads(ln) for ln in trace_path.read_text().splitlines()]
        check("keel trace lines carry exactly the five schema keys",
              all(set(ln) == {"turn", "role", "phase", "iteration", "content"} for ln in lines))
        check("stats manifest labels the outcome",
              json.loads(stats_path.read_text())["coherence_label"] == "coherent")

        pages = render_obsidian(corpus, view_ids, root / "vault")
        page = (root / "vault" / f"{claim.id}.md").read_text()
        check("claim page renders its standing challenge one edge away",
              f"undercut by [[{undercutter.id}]]" in page and undercutter.text in page)
        check("rendered one page per view node", len(pages) == len(view_ids))

    print(f"\nsmoke test passed: {len(CHECKS)} checks")


if __name__ == "__main__":
    main()
