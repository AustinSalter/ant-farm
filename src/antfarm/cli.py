"""The survey pipeline's only door into the corpus. One subcommand per
deterministic step; JSON in (--input), one JSON object out (stdout). The
workflow's clerk agent runs these commands; nothing else writes events."""

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import TypeAdapter

from antfarm import brief as brief_mod
from antfarm import farm as farm_mod
from antfarm.analysis import ach_winner, derive_e
from antfarm.cluster import CachedEmbed, EmbeddingMatcher, EmbedFn, hash_embed
from antfarm.counterfactual import persona_swap, regenerated_to_turns, swap_package
from antfarm.emission import (
    AtomBatch,
    CritiqueReport,
    CuratorOutput,
    FramingOutput,
    PersonaSwapOutput,
    ScoutRoundOutput,
    StitchOutput,
    VerificationResult,
    export_schemas,
)
from antfarm.events import append_events, read_events, status_event
from antfarm.gates import resolve_decision
from antfarm.graph import build_graph, compute_centrality, extract_cruxes
from antfarm.harvest import (
    batch_harvest,
    critique_harvest,
    framing_harvest,
    scout_harvest,
    stitch_harvest,
    verify_harvest,
)
from antfarm.reduce import Corpus, reduce_events
from antfarm.schema import Vantage, normalize_text
from antfarm.stores import CorpusStore
from antfarm.tripwires import fire_tripwire, standing_tripwires


def now_ts() -> str:
    return datetime.now(UTC).isoformat()


def question_id_for(text: str) -> str:
    digest = hashlib.sha256(f"question:{normalize_text(text)}".encode()).hexdigest()
    return f"q-{digest[:12]}"


def get_embed(corpus_dir: Path) -> EmbedFn:
    cache = corpus_dir / "emb-cache.json"
    if os.environ.get("ANTFARM_EMBED") == "hash":
        return CachedEmbed(cache, hash_embed)
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    ef = DefaultEmbeddingFunction()

    def chroma_embed(texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in ef(texts)]

    return CachedEmbed(cache, chroma_embed)


def load_corpus(corpus_dir: Path) -> Corpus:
    runs_root = corpus_dir / "runs"
    if not runs_root.exists():
        return Corpus()
    return reduce_events(read_events(runs_root),
                         matcher=EmbeddingMatcher(get_embed(corpus_dir)))


def read_payload(args: argparse.Namespace) -> Any:
    raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(
        encoding="utf-8")
    return json.loads(raw)


def stored_question(corpus_dir: Path) -> dict:
    path = corpus_dir / "question.json"
    if not path.exists():
        raise SystemExit("no question bound to this corpus - run `run-new` first")
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _vantage(run: str, farm: str, family: str, persona: str, round: int,
             sensor: Literal["model", "human"] = "model") -> Vantage:
    return Vantage(run=run, farm=farm, family=family, persona=persona,
                   round=round, sensor=sensor)


# --- handlers ---------------------------------------------------------------


def cmd_schemas(args: argparse.Namespace) -> dict:
    return export_schemas()  # type: ignore[no-any-return]


def cmd_run_new(args: argparse.Namespace) -> dict:
    corpus_dir: Path = args.corpus
    qid = question_id_for(args.question)
    qfile = corpus_dir / "question.json"
    if qfile.exists():
        stored = json.loads(qfile.read_text(encoding="utf-8"))
        if stored["question_id"] != qid:
            raise SystemExit(
                f"corpus is bound to question {stored['question_id']} "
                f"({stored['text']!r}); one corpus dir per question")
    else:
        corpus_dir.mkdir(parents=True, exist_ok=True)
        qfile.write_text(json.dumps({"question_id": qid, "text": args.question}),
                         encoding="utf-8")
    runs_root = corpus_dir / "runs"
    existing = sorted(runs_root.glob("r[0-9]*")) if runs_root.exists() else []
    run = f"r{len(existing) + 1:04d}"
    (runs_root / run).mkdir(parents=True, exist_ok=True)
    return {"run": run, "question_id": qid, "first_run": not existing}


def cmd_brief(args: argparse.Namespace) -> dict:
    question = stored_question(args.corpus)
    corpus = load_corpus(args.corpus)
    return brief_mod.warm_brief(corpus, question["question_id"], args.corpus / "runs")


def cmd_farm_init(args: argparse.Namespace) -> dict:
    question = stored_question(args.corpus)
    meta = farm_mod.FarmMeta(
        farm=args.farm, hypothesis_id=args.hypothesis_id,
        hypothesis_text=args.hypothesis_text, persona=args.persona,
        family=args.family, question_id=question["question_id"],
        question_text=question["text"])
    farm_mod.init_farm(args.corpus, args.run, args.farm, meta)
    # re-observe the hypothesis under the farm's vantage so critiques against it
    # (incl. the premortem) block THIS farm's CONCLUDE gate until sublated
    vantage = _vantage(args.run, args.farm, args.family, args.persona, round=1)
    batch = AtomBatch.model_validate(
        {"atoms": [{"type": "hypothesis", "text": args.hypothesis_text}]})
    result = batch_harvest(batch, vantage=vantage, corpus=Corpus(),
                           question_id=question["question_id"], ts=now_ts())
    append_events(args.corpus / "runs" / args.run, f"p1-farm{args.farm}-init",
                  result.events)
    return {"farm": args.farm, "hypothesis_id": args.hypothesis_id}


def cmd_harvest_framing(args: argparse.Namespace) -> dict:
    question = stored_question(args.corpus)
    output = FramingOutput.model_validate(read_payload(args))
    vantage = _vantage(args.run, "surveyor", "session", "surveyor", round=0)
    result, rivals = framing_harvest(output, vantage=vantage,
                                     question_id=question["question_id"], ts=now_ts())
    run_dir = args.corpus / "runs" / args.run
    if result.events:
        append_events(run_dir, "p1-framing", result.events)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "framing.json").write_text(output.model_dump_json(indent=2),
                                          encoding="utf-8")
    return {"rivals": rivals, "dissolved": output.dissolve.dissolved,
            "rejected": result.rejected}


def cmd_harvest_scout(args: argparse.Namespace) -> dict:
    question = stored_question(args.corpus)
    output = ScoutRoundOutput.model_validate(read_payload(args))
    corpus = load_corpus(args.corpus)
    d = farm_mod.farm_dir(args.corpus, args.run, args.farm)
    vantage = _vantage(args.run, args.farm, args.family, args.persona, args.round)
    result = scout_harvest(output, vantage=vantage, corpus=corpus,
                           question_id=question["question_id"], ts=now_ts(),
                           start_turn=farm_mod.next_turn_index(d))
    append_events(args.corpus / "runs" / args.run,
                  f"p2-farm{args.farm}-r{args.round:02d}", result.events)
    farm_mod.append_turns(d, result.turns)
    if output.falsification_triggers:
        farm_mod.append_triggers(d, output.falsification_triggers)
    if output.ledger_entry is not None:
        farm_mod.append_ledger(d, output.ledger_entry)
    return {"atom_ids": result.atom_ids, "rejected": result.rejected,
            "unresolved": result.unresolved, "turns_appended": len(result.turns)}


def cmd_harvest_critique(args: argparse.Namespace) -> dict:
    question = stored_question(args.corpus)
    report = CritiqueReport.model_validate(read_payload(args))
    corpus = load_corpus(args.corpus)
    d = farm_mod.farm_dir(args.corpus, args.run, args.farm)
    meta = farm_mod.read_meta(d)
    vantage = _vantage(args.run, args.farm, args.family, "blind-critic", args.round)
    result = critique_harvest(report, vantage=vantage, corpus=corpus,
                              hypothesis_id=meta.hypothesis_id,
                              question_id=question["question_id"], ts=now_ts(),
                              start_turn=farm_mod.next_turn_index(d))
    append_events(args.corpus / "runs" / args.run,
                  f"p3-farm{args.farm}-r{args.round:02d}", result.events)
    farm_mod.append_turns(d, result.turns)
    farm_mod.write_critique(d, args.round, report)
    return {"atom_ids": result.atom_ids, "rejected": result.rejected,
            "unresolved": result.unresolved}


def cmd_harvest_verify(args: argparse.Namespace) -> dict:
    results = TypeAdapter(list[VerificationResult]).validate_python(read_payload(args))
    corpus = load_corpus(args.corpus)
    vantage = _vantage(args.run, "verifier", "session", "verifier", round=0)
    result = verify_harvest(results, corpus=corpus, vantage=vantage, ts=now_ts())
    if result.events:
        append_events(args.corpus / "runs" / args.run, "p4-verify", result.events)
    return {"verified": result.atom_ids, "unresolved": result.unresolved}


def cmd_harvest_stitch(args: argparse.Namespace) -> dict:
    question = stored_question(args.corpus)
    output = StitchOutput.model_validate(read_payload(args))
    corpus = load_corpus(args.corpus)
    vantage = _vantage(args.run, "stitcher", "session", "stitcher", round=0)
    result = stitch_harvest(output, vantage=vantage, corpus=corpus,
                            question_id=question["question_id"], ts=now_ts())
    if result.events:
        append_events(args.corpus / "runs" / args.run, "p5-stitch", result.events)
    after = load_corpus(args.corpus)
    cent = compute_centrality(build_graph(after))
    declaration = {
        "kind": output.declaration_kind,
        "summary": output.declaration_summary,
        "positions": [p.model_dump() for p in output.positions],
        "dissolved": output.dissolve.dissolved,
        "ach": ach_winner(after, question["question_id"]),
        "e_band": derive_e(after, question["question_id"]),
        "cruxes": [{"id": nid, "text": after.nodes[nid].text}
                   for nid in extract_cruxes(after, cent)],
    }
    (args.corpus / "runs" / args.run / "declaration.json").write_text(
        json.dumps(declaration, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"declaration": declaration, "rejected": result.rejected,
            "unresolved": result.unresolved}


def cmd_harvest_atoms(args: argparse.Namespace) -> dict:
    question = stored_question(args.corpus)
    batch = AtomBatch.model_validate(read_payload(args))
    corpus = load_corpus(args.corpus)
    vantage = _vantage(args.run, args.farm, args.family, args.persona, args.round,
                       sensor=args.sensor)
    result = batch_harvest(batch, vantage=vantage, corpus=corpus,
                           question_id=question["question_id"], ts=now_ts())
    if result.events:
        append_events(args.corpus / "runs" / args.run, f"p6-{args.farm}", result.events)
    return {"atom_ids": result.atom_ids, "rejected": result.rejected,
            "unresolved": result.unresolved}


def cmd_gate(args: argparse.Namespace) -> dict:
    output = ScoutRoundOutput.model_validate(read_payload(args))
    corpus = load_corpus(args.corpus)
    d = farm_mod.farm_dir(args.corpus, args.run, args.farm)
    result = resolve_decision(
        scout_decision=output.decision, corpus=corpus, farm=args.farm,
        triggers=farm_mod.read_triggers(d), ledger=farm_mod.read_ledger(d),
        final_round=args.final_round)
    return result.model_dump()


def cmd_verification_queue(args: argparse.Namespace) -> list[dict]:
    return brief_mod.verification_queue(load_corpus(args.corpus))


def cmd_probe(args: argparse.Namespace) -> dict:
    payload = read_payload(args)
    corpus = load_corpus(args.corpus)
    return brief_mod.probe(corpus, get_embed(args.corpus), payload["text"])


def cmd_query(args: argparse.Namespace) -> list[dict]:
    chroma_dir = args.corpus / "chroma"
    if not chroma_dir.exists():
        return []
    store = CorpusStore.persistent(chroma_dir, get_embed(args.corpus))
    try:
        return store.query(args.collection, args.text, n=args.n)
    except Exception:  # collection missing before first materialize
        return []


def cmd_tripwires_list(args: argparse.Namespace) -> list[dict]:
    return standing_tripwires(load_corpus(args.corpus))


def cmd_tripwire_fire(args: argparse.Namespace) -> dict:
    payload = read_payload(args)
    question = stored_question(args.corpus)
    corpus = load_corpus(args.corpus)
    vantage = _vantage(args.run, "sentinel", "session", "sentinel", round=0)
    events, affected = fire_tripwire(corpus, args.id, payload["evidence"],
                                     vantage=vantage,
                                     question_id=question["question_id"], ts=now_ts())
    append_events(args.corpus / "runs" / args.run, "p0-sentinel", events)
    return {"affected": affected}


def cmd_stitch_brief(args: argparse.Namespace) -> dict:
    return brief_mod.stitch_brief(load_corpus(args.corpus), args.corpus, args.run)


def cmd_farm_outcome(args: argparse.Namespace) -> dict:
    d = farm_mod.farm_dir(args.corpus, args.run, args.farm)
    farm_mod.write_outcome(d, args.decision, args.died_because)
    if args.decision == "CONCEDE":
        meta = farm_mod.read_meta(d)
        append_events(args.corpus / "runs" / args.run, f"p2z-farm{args.farm}-outcome",
                      [status_event(meta.hypothesis_id, "conceded", ts=now_ts(),
                                    died_because=args.died_because)])
    return {"farm": args.farm, "decision": args.decision}


def cmd_persona_swap_prepare(args: argparse.Namespace) -> dict:
    d = farm_mod.farm_dir(args.corpus, args.run, args.farm)
    return swap_package(farm_mod.read_turns(d), args.start_iteration)


def cmd_persona_swap_write(args: argparse.Namespace) -> dict:
    output = PersonaSwapOutput.model_validate(read_payload(args))
    d = farm_mod.farm_dir(args.corpus, args.run, args.farm)
    host = farm_mod.read_turns(d)
    swapped = persona_swap(host, regenerated_to_turns(output), args.start_iteration)
    out_dir = args.corpus / "exports" / args.run / f"{args.farm}-persona-swap"
    out_dir.mkdir(parents=True, exist_ok=True)
    trace = out_dir / "trace.jsonl"
    with trace.open("w", encoding="utf-8") as f:
        for t in swapped:
            f.write(t.model_dump_json() + "\n")
    (out_dir / "stats.json").write_text(json.dumps({
        "counterfactual": "persona_swap",
        "start_iteration": args.start_iteration,
        "turns": len(swapped)}), encoding="utf-8")
    return {"trace": str(trace), "turns": len(swapped)}


def cmd_map_write(args: argparse.Namespace) -> dict:
    output = CuratorOutput.model_validate(read_payload(args))
    vault = args.corpus / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    path = vault / "MAP.md"
    path.write_text(output.map_markdown, encoding="utf-8")
    return {"path": str(path)}


HANDLERS: dict[str, Any] = {
    "schemas": cmd_schemas,
    "run-new": cmd_run_new,
    "brief": cmd_brief,
    "farm-init": cmd_farm_init,
    "harvest-framing": cmd_harvest_framing,
    "harvest-scout": cmd_harvest_scout,
    "harvest-critique": cmd_harvest_critique,
    "harvest-verify": cmd_harvest_verify,
    "harvest-stitch": cmd_harvest_stitch,
    "harvest-atoms": cmd_harvest_atoms,
    "gate": cmd_gate,
    "verification-queue": cmd_verification_queue,
    "probe": cmd_probe,
    "query": cmd_query,
    "tripwires-list": cmd_tripwires_list,
    "tripwire-fire": cmd_tripwire_fire,
    "stitch-brief": cmd_stitch_brief,
    "farm-outcome": cmd_farm_outcome,
    "persona-swap-prepare": cmd_persona_swap_prepare,
    "persona-swap-write": cmd_persona_swap_write,
    "map-write": cmd_map_write,
}


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--corpus", type=Path, default=Path("corpus"))
    common.add_argument("--input", default="-")

    parser = argparse.ArgumentParser(prog="antfarm")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add(name: str, **kwargs: Any) -> None:
        sp = sub.add_parser(name, parents=[common])
        for flag, kw in kwargs.items():
            sp.add_argument(flag, **kw)  # type: ignore[arg-type]

    add("schemas")
    add("run-new", **{"--question": {"required": True}})
    add("brief")
    add("farm-init", **{"--run": {"required": True}, "--farm": {"required": True},
                        "--hypothesis-id": {"required": True},
                        "--hypothesis-text": {"required": True},
                        "--persona": {"required": True}, "--family": {"required": True}})
    add("harvest-framing", **{"--run": {"required": True}})
    add("harvest-scout", **{"--run": {"required": True}, "--farm": {"required": True},
                            "--round": {"required": True, "type": int},
                            "--family": {"required": True},
                            "--persona": {"required": True}})
    add("harvest-critique", **{"--run": {"required": True}, "--farm": {"required": True},
                               "--round": {"required": True, "type": int},
                               "--family": {"default": "session"}})
    add("harvest-verify", **{"--run": {"required": True}})
    add("harvest-stitch", **{"--run": {"required": True}})
    add("harvest-atoms", **{"--run": {"required": True}, "--farm": {"required": True},
                            "--round": {"default": 0, "type": int},
                            "--family": {"default": "session"},
                            "--persona": {"required": True},
                            "--sensor": {"default": "model",
                                         "choices": ["model", "human"]}})
    add("gate", **{"--run": {"required": True}, "--farm": {"required": True},
                   "--final-round": {"action": "store_true"}})
    add("verification-queue")
    add("probe")
    add("query", **{"--collection": {"required": True}, "--text": {"required": True},
                    "--n": {"default": 8, "type": int}})
    add("tripwires-list")
    add("tripwire-fire", **{"--run": {"required": True}, "--id": {"required": True}})
    add("stitch-brief", **{"--run": {"required": True}})
    add("farm-outcome", **{"--run": {"required": True}, "--farm": {"required": True},
                           "--decision": {"required": True},
                           "--died-because": {"default": None}})
    add("persona-swap-prepare", **{"--run": {"required": True},
                                   "--farm": {"required": True},
                                   "--start-iteration": {"required": True, "type": int}})
    add("persona-swap-write", **{"--run": {"required": True},
                                 "--farm": {"required": True},
                                 "--start-iteration": {"required": True, "type": int}})
    add("map-write")
    return parser


def main(argv: list[str] | None = None) -> Any:
    args = build_parser().parse_args(argv)
    result = HANDLERS[args.cmd](args)
    print(json.dumps(result, ensure_ascii=False))
    return result
