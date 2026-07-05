"""Script-enforced farm decisions (spec §5 Phase 2). The scout proposes;
resolve_decision disposes. CONCLUDE needs >=1 HIGH falsification trigger,
no un-sublated undercutters against the farm's atoms, and a clean
degeneration ledger. Two consecutive novel-content-free patches force
ELEVATE (Lakatos, spec §7)."""

from pydantic import BaseModel, Field

from antfarm.emission import FarmDecision, TriggerEmission
from antfarm.graph import find_unsublated_undercutters
from antfarm.reduce import Corpus
from antfarm.transcript import LedgerEntry


class GateResult(BaseModel):
    decision: FarmDecision
    forced: bool = False
    reasons: list[str] = Field(default_factory=list)


def degeneration_forced(ledger: list[LedgerEntry]) -> bool:
    return (len(ledger) >= 2
            and not ledger[-1].novel_content
            and not ledger[-2].novel_content)


def farm_node_ids(corpus: Corpus, farm: str) -> set[str]:
    return {nid for nid, node in corpus.nodes.items()
            if any(v.farm == farm for v in node.vantages)}


_EXHAUSTED = "round budget exhausted"
_DEGENERATE = "degeneration ledger: two consecutive novel-content-free patches"


def conclude_blockers(corpus: Corpus, farm: str, triggers: list[TriggerEmission],
                      ledger: list[LedgerEntry]) -> list[str]:
    reasons = []
    if not any(t.severity == "high" for t in triggers):
        reasons.append("no HIGH-severity falsification trigger on record")
    mine = farm_node_ids(corpus, farm)
    standing = [(src, dst) for src, dst in find_unsublated_undercutters(corpus)
                if dst in mine]
    if standing:
        reasons.append(
            f"{len(standing)} un-sublated undercutter(s) against this farm's atoms")
    if degeneration_forced(ledger):
        reasons.append(_DEGENERATE)
    return reasons


def resolve_decision(*, scout_decision: FarmDecision, corpus: Corpus, farm: str,
                     triggers: list[TriggerEmission], ledger: list[LedgerEntry],
                     final_round: bool) -> GateResult:
    if scout_decision in ("CONCEDE", "ELEVATE"):
        return GateResult(decision=scout_decision)
    if degeneration_forced(ledger):
        return GateResult(decision="ELEVATE", forced=True, reasons=[_DEGENERATE])
    if scout_decision == "CONCLUDE":
        reasons = conclude_blockers(corpus, farm, triggers, ledger)
        if not reasons:
            return GateResult(decision="CONCLUDE")
        if final_round:
            return GateResult(decision="ELEVATE", forced=True,
                              reasons=[*reasons, _EXHAUSTED])
        return GateResult(decision="CONTINUE", forced=True, reasons=reasons)
    if final_round:
        return GateResult(decision="ELEVATE", forced=True, reasons=[_EXHAUSTED])
    return GateResult(decision="CONTINUE")
