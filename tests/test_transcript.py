import json

import pytest

from antfarm.transcript import (
    LedgerEntry,
    Outcome,
    Turn,
    VerificationStats,
    coherence_label,
    write_transcript,
)
from helpers import V

TURNS = [
    Turn(
        turn=0,
        role="user",
        phase=None,
        iteration=1,
        content="Question: is rooftop solar a good investment?",
    ),
    Turn(
        turn=1,
        role="assistant",
        phase="expand",
        iteration=1,
        content="Payback periods below ten years in most states.",
    ),
    Turn(
        turn=2,
        role="assistant",
        phase="compress",
        iteration=1,
        content="Thesis: rooftop solar pays back in a decade.",
    ),
    Turn(
        turn=3,
        role="assistant",
        phase="sublate",
        iteration=2,
        content="Critique survives; qualify thesis to net-metering.",
    ),
]

# spec 9.2: export carries decision, degeneration-ledger state,
# verification stats
OUTCOME = Outcome(
    decision="CONCLUDE",
    ledger_clean=True,
    ledger=[
        LedgerEntry(
            trigger="net-metering rollback critique",
            change="qualified thesis to net-metering states",
            novel_content=True,
        )
    ],
    verification=VerificationStats(atoms_emitted=12, atoms_verified=9),
)


def test_trace_jsonl_matches_keel_schema_exactly(tmp_path):
    trace_path, _ = write_transcript(tmp_path / "farmA", TURNS, V, OUTCOME)
    lines = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert len(lines) == 4
    # exact keel traces/ schema: these five keys, no others
    assert all(set(line) == {"turn", "role", "phase", "iteration", "content"} for line in lines)
    assert lines[3] == {"turn": 3, "role": "assistant", "phase": "sublate",
                        "iteration": 2, "content": TURNS[3].content}


def test_stats_manifest_carries_vantage_outcome_label(tmp_path):
    outcome = OUTCOME.model_copy(update={"refuted": True})
    _, stats_path = write_transcript(tmp_path / "farmA", TURNS, V, outcome)
    stats = json.loads(stats_path.read_text())
    assert stats["vantage"]["farm"] == "A"
    assert stats["outcome"]["decision"] == "CONCLUDE"
    assert stats["outcome"]["ledger"][0]["novel_content"] is True
    assert stats["outcome"]["verification"] == {"atoms_emitted": 12, "atoms_verified": 9}
    assert stats["coherence_label"] == "coherent_refuted"
    assert stats["turns"] == 4 and stats["iterations"] == 2
    assert stats["approx_tokens"] > 0


@pytest.mark.parametrize("outcome,expected", [
    (Outcome(decision="CONCEDE", ledger_clean=True,
             died_because="rival explained the evidence"), "conceded"),
    (Outcome(decision="CONCLUDE", ledger_clean=True), "coherent"),
    (Outcome(decision="CONCLUDE", ledger_clean=True, refuted=True), "coherent_refuted"),
    (Outcome(decision="ELEVATE", ledger_clean=False), "elevated"),
])
def test_label_discipline(outcome, expected):
    # spec 9.2: CONCEDE is a dialectical outcome, never exported as degraded
    assert coherence_label(outcome) == expected
