"""Per-farm state directory: the scout's continuity, the critic's input,
Phase 7's transcript source. Layout: farms/<run>/<farm>/{meta.json,
turns.jsonl, ledger.jsonl, triggers.jsonl, critiques/rNN.json, outcome.json}."""

import json
from pathlib import Path

from pydantic import BaseModel

from antfarm.emission import CritiqueReport, TriggerEmission
from antfarm.transcript import LedgerEntry, Turn


class FarmMeta(BaseModel):
    farm: str
    hypothesis_id: str
    hypothesis_text: str
    persona: str
    family: str
    question_id: str
    question_text: str


def farm_dir(corpus_dir: Path, run: str, farm: str) -> Path:
    return corpus_dir / "farms" / run / farm


def init_farm(corpus_dir: Path, run: str, farm: str, meta: FarmMeta) -> Path:
    d = farm_dir(corpus_dir, run, farm)
    (d / "critiques").mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    brief = (f"Question: {meta.question_text}\n"
             f"Assigned hypothesis: {meta.hypothesis_text}\n"
             f"Persona: {meta.persona}")
    append_turns(d, [Turn(turn=0, role="user", phase=None, iteration=1, content=brief)])
    return d


def read_meta(d: Path) -> FarmMeta:
    return FarmMeta.model_validate_json((d / "meta.json").read_text(encoding="utf-8"))


def _append_jsonl(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def append_turns(d: Path, turns: list[Turn]) -> None:
    _append_jsonl(d / "turns.jsonl", [t.model_dump_json() for t in turns])


def read_turns(d: Path) -> list[Turn]:
    return [Turn.model_validate(x) for x in _read_jsonl(d / "turns.jsonl")]


def next_turn_index(d: Path) -> int:
    return len(read_turns(d))


def append_ledger(d: Path, entry: LedgerEntry) -> None:
    _append_jsonl(d / "ledger.jsonl", [entry.model_dump_json()])


def read_ledger(d: Path) -> list[LedgerEntry]:
    return [LedgerEntry.model_validate(x) for x in _read_jsonl(d / "ledger.jsonl")]


def append_triggers(d: Path, triggers: list[TriggerEmission]) -> None:
    _append_jsonl(d / "triggers.jsonl", [t.model_dump_json() for t in triggers])


def read_triggers(d: Path) -> list[TriggerEmission]:
    return [TriggerEmission.model_validate(x) for x in _read_jsonl(d / "triggers.jsonl")]


def write_critique(d: Path, round: int, report: CritiqueReport) -> Path:
    path = d / "critiques" / f"r{round:02d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_outcome(d: Path, decision: str, died_because: str | None) -> None:
    (d / "outcome.json").write_text(
        json.dumps({"decision": decision, "died_because": died_because}),
        encoding="utf-8")


def read_outcome(d: Path) -> dict | None:
    path = d / "outcome.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def last_compressed(d: Path) -> str | None:
    compressed = [t.content for t in read_turns(d) if t.phase == "compress"]
    return compressed[-1] if compressed else None
