from antfarm.emission import (
    AtomBatch,
    AtomEmission,
    EdgeEmission,
    ScoutRoundOutput,
    SublationItem,
)
from antfarm.harvest import batch_harvest, resolve_ref, scout_harvest
from antfarm.reduce import Corpus
from antfarm.schema import atom_id
from helpers import make_corpus_node, make_vantage

V = make_vantage(farm="A", round=2)
TS = "2026-07-04T00:00:00Z"
Q = "q-1"

CLAIM = "Grid storage lags panel deployment by several years."
EVIDENCE = "California curtailed 2.4 TWh of solar generation in 2024."


def _batch(**kw):
    return AtomBatch(**kw)


def test_batch_harvest_stamps_vantage_and_computes_ids():
    result = batch_harvest(
        _batch(atoms=[AtomEmission(type="claim", text=CLAIM)]),
        vantage=V, corpus=Corpus(), question_id=Q, ts=TS)
    assert result.atom_ids == [atom_id("claim", CLAIM)]
    payload = result.events[0]["payload"]
    assert payload["vantage"]["farm"] == "A" and payload["ts"] == TS
    assert payload["verified"] is False  # emissions can never claim verification


def test_non_self_contained_atom_is_rejected_not_repaired():
    result = batch_harvest(
        _batch(atoms=[AtomEmission(type="claim", text="This proves the thesis."),
                      AtomEmission(type="claim", text=CLAIM)]),
        vantage=V, corpus=Corpus(), question_id=Q, ts=TS)
    assert len(result.atom_ids) == 1
    assert result.rejected[0]["text"] == "This proves the thesis."


def test_edges_resolve_batch_text_and_corpus_id():
    existing = make_corpus_node("Solar deployment doubled between 2020 and 2024.")
    corpus = Corpus(nodes={existing.id: existing})
    result = batch_harvest(
        _batch(atoms=[AtomEmission(type="claim", text=CLAIM),
                      AtomEmission(type="evidence", text=EVIDENCE, strength=4)],
               edges=[EdgeEmission(src=EVIDENCE, dst=CLAIM, rel="supports",
                                   warrant="curtailment evidences a storage bottleneck"),
                      EdgeEmission(src=CLAIM, dst=existing.id, rel="qualifies")]),
        vantage=V, corpus=corpus, question_id=Q, ts=TS)
    edge_events = [e for e in result.events if e["kind"] == "edge"]
    assert len(edge_events) == 2
    assert edge_events[0]["payload"]["src"] == atom_id("evidence", EVIDENCE)
    assert edge_events[1]["payload"]["dst"] == existing.id


def test_edge_to_unknown_ref_is_reported_not_written():
    result = batch_harvest(
        _batch(atoms=[AtomEmission(type="claim", text=CLAIM)],
               edges=[EdgeEmission(src=CLAIM, dst="never emitted anywhere", rel="rebuts")]),
        vantage=V, corpus=Corpus(), question_id=Q, ts=TS)
    assert not [e for e in result.events if e["kind"] == "edge"]
    assert result.unresolved == [{"src": CLAIM, "dst": "never emitted anywhere",
                                  "rel": "rebuts"}]


def test_edge_from_rejected_atom_is_unresolved():
    result = batch_harvest(
        _batch(atoms=[AtomEmission(type="claim", text="It follows trivially.")],
               edges=[EdgeEmission(src="It follows trivially.", dst=CLAIM, rel="rebuts")]),
        vantage=V, corpus=Corpus(), question_id=Q, ts=TS)
    assert result.rejected and result.unresolved


def test_resolve_ref_matches_corpus_text_exactly():
    existing = make_corpus_node("Solar deployment doubled between 2020 and 2024.")
    corpus = Corpus(nodes={existing.id: existing})
    assert resolve_ref("  solar deployment DOUBLED between 2020 and 2024. ",
                       {}, corpus) == existing.id
    assert resolve_ref("c-000000000000", {}, corpus) is None  # unknown id


SCOUT = ScoutRoundOutput(
    sublation=[SublationItem(critique="Curtailment may reflect transmission, not storage.",
                             disposition="qualified",
                             response="Qualified the thesis to storage-plus-transmission.")],
    expansion="Anomaly: curtailment rose while battery installs also rose.",
    atoms=[AtomEmission(type="claim", text=CLAIM)],
    falsification_triggers=[],
    compressed_state="Thesis: storage (with transmission) binds solar growth.",
    confidence_r="med", confidence_c="med",
    decision="CONTINUE",
)


def test_scout_harvest_builds_sublate_expand_compress_turns():
    result = scout_harvest(SCOUT, vantage=V, corpus=Corpus(), question_id=Q, ts=TS,
                           start_turn=5)
    assert [(t.turn, t.phase, t.iteration) for t in result.turns] == [
        (5, "sublate", 2), (6, "expand", 2), (7, "compress", 2)]
    assert result.turns[0].role == "assistant"
    assert "qualified" in result.turns[0].content
    assert result.turns[2].content == SCOUT.compressed_state


def test_scout_harvest_round_one_has_no_sublate_turn():
    first = SCOUT.model_copy(update={"sublation": []})
    result = scout_harvest(first, vantage=make_vantage(farm="A", round=1),
                           corpus=Corpus(), question_id=Q, ts=TS, start_turn=1)
    assert [t.phase for t in result.turns] == ["expand", "compress"]
