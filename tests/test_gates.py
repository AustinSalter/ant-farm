from antfarm.emission import TriggerEmission
from antfarm.gates import degeneration_forced, farm_node_ids, resolve_decision
from antfarm.reduce import Corpus
from antfarm.transcript import LedgerEntry
from helpers import make_corpus_node, make_edge

HIGH = TriggerEmission(text="A 2027 storage glut with flat solar growth falsifies this.",
                       severity="high")
LOW = TriggerEmission(text="A mild price dip would be surprising.", severity="low")


def _entry(novel: bool) -> LedgerEntry:
    return LedgerEntry(trigger="critique", change="patched", novel_content=novel)


def _farm_corpus(with_undercutter: bool) -> Corpus:
    # helpers' default vantage is farm "A", so every node here is farm A's
    thesis = make_corpus_node("Storage constraints bind solar growth through 2030.",
                              type="hypothesis")
    corpus = Corpus(nodes={thesis.id: thesis})
    if with_undercutter:
        attack = make_corpus_node("Storage statistics conflate contracted capacity.")
        corpus.nodes[attack.id] = attack
        corpus.edges.append(make_edge(attack.id, thesis.id, "undercuts"))
    return corpus


def test_degeneration_two_consecutive_content_free_patches():
    assert not degeneration_forced([_entry(False)])
    assert not degeneration_forced([_entry(False), _entry(True), _entry(False)])
    assert degeneration_forced([_entry(True), _entry(False), _entry(False)])


def test_farm_node_ids_uses_any_sighting_vantage():
    corpus = _farm_corpus(with_undercutter=False)
    assert farm_node_ids(corpus, "A") == set(corpus.nodes)
    assert farm_node_ids(corpus, "B") == set()


def test_conclude_blocked_without_high_trigger():
    result = resolve_decision(scout_decision="CONCLUDE",
                              corpus=_farm_corpus(False), farm="A",
                              triggers=[LOW], ledger=[], final_round=False)
    assert result.decision == "CONTINUE" and result.forced
    assert any("HIGH-severity" in r for r in result.reasons)


def test_conclude_blocked_by_unsublated_undercutter():
    result = resolve_decision(scout_decision="CONCLUDE",
                              corpus=_farm_corpus(True), farm="A",
                              triggers=[HIGH], ledger=[], final_round=False)
    assert result.decision == "CONTINUE"
    assert any("undercutter" in r for r in result.reasons)


def test_conclude_passes_when_gates_clear():
    corpus = _farm_corpus(True)
    # answer the undercutter with a live rebuttal - the challenge is no longer standing
    answer = make_corpus_node("Contracted-capacity inflation is corrected in the dataset.")
    corpus.nodes[answer.id] = answer
    attack_id = next(nid for nid, n in corpus.nodes.items()
                     if n.text.startswith("Storage statistics"))
    corpus.edges.append(make_edge(answer.id, attack_id, "rebuts"))
    result = resolve_decision(scout_decision="CONCLUDE", corpus=corpus, farm="A",
                              triggers=[HIGH, LOW], ledger=[_entry(True)],
                              final_round=False)
    assert result.decision == "CONCLUDE" and not result.forced


def test_concede_and_elevate_pass_through():
    for decision in ("CONCEDE", "ELEVATE"):
        result = resolve_decision(scout_decision=decision, corpus=Corpus(), farm="A",
                                  triggers=[], ledger=[], final_round=False)
        assert result.decision == decision and not result.forced


def test_degeneration_forces_elevate_on_continue():
    result = resolve_decision(scout_decision="CONTINUE", corpus=Corpus(), farm="A",
                              triggers=[], ledger=[_entry(False), _entry(False)],
                              final_round=False)
    assert result.decision == "ELEVATE" and result.forced


def test_final_round_never_returns_continue():
    blocked = resolve_decision(scout_decision="CONCLUDE", corpus=_farm_corpus(False),
                               farm="A", triggers=[], ledger=[], final_round=True)
    assert blocked.decision == "ELEVATE"
    assert any("round budget" in r for r in blocked.reasons)
    idle = resolve_decision(scout_decision="CONTINUE", corpus=Corpus(), farm="A",
                            triggers=[], ledger=[], final_round=True)
    assert idle.decision == "ELEVATE" and idle.forced
