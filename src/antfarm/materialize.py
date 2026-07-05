"""Phase 7: rebuild the derived world from the event log - view gate, chroma
stores, Obsidian render, keel transcript exports, tripwire registration."""

from pathlib import Path

from antfarm.cluster import EmbeddingMatcher, EmbedFn
from antfarm.events import append_events, read_events
from antfarm.farm import read_ledger, read_meta, read_outcome, read_triggers, read_turns
from antfarm.gates import degeneration_forced
from antfarm.graph import build_graph, compute_centrality, compute_view
from antfarm.reduce import Corpus, reduce_events
from antfarm.render import render_obsidian
from antfarm.schema import Vantage
from antfarm.stores import CorpusStore
from antfarm.transcript import Outcome, VerificationStats, write_transcript
from antfarm.tripwires import register_tripwires


def _farm_stats(corpus: Corpus, farm: str) -> VerificationStats:
    emitted = [n for n in corpus.nodes.values()
               if any(v.farm == farm for v in n.vantages)]
    return VerificationStats(atoms_emitted=len(emitted),
                             atoms_verified=sum(1 for n in emitted if n.verified))


def materialize(corpus_dir: Path, run: str, embed: EmbedFn, ts: str) -> dict:
    runs_root = corpus_dir / "runs"
    farms_root = corpus_dir / "farms" / run
    farm_dirs = (sorted(d for d in farms_root.iterdir() if (d / "meta.json").exists())
                 if farms_root.exists() else [])

    # 1. register this run's HIGH-severity falsification triggers as tripwires
    corpus = reduce_events(read_events(runs_root), matcher=EmbeddingMatcher(embed))
    trip_events: list[dict] = []
    for d in farm_dirs:
        meta = read_meta(d)
        vantage = Vantage(run=run, farm=meta.farm, family=meta.family,
                          persona=meta.persona, round=0, sensor="model")
        trip_events.extend(register_tripwires(
            read_triggers(d), meta.hypothesis_id, vantage=vantage,
            question_id=meta.question_id, ts=ts))
    if trip_events:
        append_events(runs_root / run, "p7-materialize", trip_events)
        corpus = reduce_events(read_events(runs_root), matcher=EmbeddingMatcher(embed))

    # 2. view gate, stores, render
    graph = build_graph(corpus)
    cent = compute_centrality(graph)
    view_ids = compute_view(corpus, cent)
    store = CorpusStore.persistent(corpus_dir / "chroma", embed)
    store.rebuild(corpus, view_ids)
    pages = render_obsidian(corpus, view_ids, corpus_dir / "vault")

    # 3. keel transcript exports (spec §4.5, §9.2)
    exported = []
    for d in farm_dirs:
        meta = read_meta(d)
        turns = read_turns(d)
        ledger = read_ledger(d)
        stored = read_outcome(d) or {"decision": "ELEVATE", "died_because": None}
        hypothesis = corpus.nodes.get(meta.hypothesis_id)
        refuted = (stored["decision"] == "CONCLUDE"
                   and hypothesis is not None and hypothesis.status != "live")
        outcome = Outcome(decision=stored["decision"], ledger=ledger,
                          ledger_clean=not degeneration_forced(ledger),
                          verification=_farm_stats(corpus, meta.farm),
                          refuted=refuted, died_because=stored.get("died_because"))
        last_round = max((t.iteration for t in turns), default=1)
        vantage = Vantage(run=run, farm=meta.farm, family=meta.family,
                          persona=meta.persona, round=last_round, sensor="model")
        write_transcript(corpus_dir / "exports" / run / meta.farm, turns, vantage,
                         outcome)
        exported.append(meta.farm)

    return {"nodes": len(corpus.nodes), "edges": len(corpus.edges),
            "view_size": len(view_ids), "pages": len(pages),
            "farms_exported": exported,
            "tripwires_registered": sum(1 for e in trip_events if e["kind"] == "node")}
