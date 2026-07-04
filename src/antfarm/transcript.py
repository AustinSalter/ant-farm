import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from antfarm.schema import Vantage


class Turn(BaseModel):
    turn: int
    role: Literal["user", "assistant", "system"]
    phase: Literal["sublate", "expand", "compress", "critique"] | None = None
    iteration: int
    content: str


class LedgerEntry(BaseModel):
    """One Lakatos revision-ledger row (spec §7): what triggered a patch and
    whether the patch carried novel content."""

    trigger: str
    change: str
    novel_content: bool


class VerificationStats(BaseModel):
    atoms_emitted: int = 0
    atoms_verified: int = 0


class Outcome(BaseModel):
    decision: Literal["CONCLUDE", "CONCEDE", "ELEVATE"]
    ledger_clean: bool
    ledger: list[LedgerEntry] = Field(default_factory=list)
    verification: VerificationStats = Field(default_factory=VerificationStats)
    refuted: bool = False
    died_because: str | None = None


def coherence_label(outcome: Outcome) -> str:
    if outcome.decision == "CONCLUDE":
        return "coherent_refuted" if outcome.refuted else "coherent"
    if outcome.decision == "CONCEDE":
        return "conceded"
    return "elevated"


def write_transcript(farm_dir: Path, turns: list[Turn], vantage: Vantage,
                     outcome: Outcome) -> tuple[Path, Path]:
    farm_dir.mkdir(parents=True, exist_ok=True)
    trace_path = farm_dir / "trace.jsonl"
    with trace_path.open("w", encoding="utf-8") as f:
        for t in turns:
            f.write(json.dumps(t.model_dump(), ensure_ascii=False) + "\n")
    stats = {
        "vantage": vantage.model_dump(),
        "outcome": outcome.model_dump(),
        "coherence_label": coherence_label(outcome),
        "turns": len(turns),
        "iterations": max((t.iteration for t in turns), default=0),
        "approx_tokens": sum(len(t.content) for t in turns) // 4,
    }
    stats_path = farm_dir / "stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2))
    return trace_path, stats_path
