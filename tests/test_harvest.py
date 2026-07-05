from antfarm.emission import (
    ACHCell,
    AtomBatch,
    AtomEmission,
    BasinPosition,
    CritiqueFinding,
    CritiqueReport,
    Dissolve,
    EdgeEmission,
    FramingOutput,
    RivalHypothesis,
    ScoutRoundOutput,
    StitchInvestigation,
    StitchOutput,
    SublationItem,
    VerificationResult,
)
from antfarm.events import node_event
from antfarm.harvest import (
    batch_harvest,
    critique_harvest,
    framing_harvest,
    resolve_ref,
    scout_harvest,
    stitch_harvest,
    verify_harvest,
)
from antfarm.reduce import Corpus, reduce_events
from antfarm.schema import Node, atom_id
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


HYP = "Storage constraints bind solar growth through 2030."
CRITIQUE_V = make_vantage(farm="A", persona="blind-critic", round=1)


def _hyp_corpus():
    hyp = make_corpus_node(HYP, type="hypothesis")
    claim = make_corpus_node(CLAIM)
    return Corpus(nodes={hyp.id: hyp, claim.id: claim}), hyp.id, claim.id


def test_critique_findings_become_claims_with_challenge_edges():
    corpus, hyp_id, claim_id = _hyp_corpus()
    report = CritiqueReport(
        findings=[CritiqueFinding(
            target_text=CLAIM, kind="warrant_probe", classification="undercutting",
            severity="high",
            text="Storage-lag statistics conflate contracted and installed capacity.")],
        premortem="The thesis failed by 2027 because interconnection queues cleared.",
        summary="One HIGH warrant probe; premortem names interconnection risk.")
    result = critique_harvest(report, vantage=CRITIQUE_V, corpus=corpus,
                              hypothesis_id=hyp_id, question_id=Q, ts=TS, start_turn=4)
    kinds = [(e["kind"], e["payload"].get("rel")) for e in result.events]
    assert ("edge", "undercuts") in kinds
    edge_payloads = [e["payload"] for e in result.events if e["kind"] == "edge"]
    assert {p["dst"] for p in edge_payloads} == {claim_id, hyp_id}
    assert [t.phase for t in result.turns] == ["critique"]
    assert result.turns[0].role == "user" and result.turns[0].turn == 4


def test_framing_rivals_become_hypothesis_nodes():
    framing = FramingOutput(
        stasis="quality", altitude="market", dissolve=Dissolve(),
        reference_class="cost-decline theses", base_rate="about half",
        zwicky_dimensions=[],
        rivals=[RivalHypothesis(text=HYP),
                RivalHypothesis(text="No single constraint binds solar growth.",
                                is_null=True)])
    result, rivals = framing_harvest(framing, vantage=make_vantage(farm="surveyor"),
                                     question_id=Q, ts=TS)
    assert [e["payload"]["type"] for e in result.events] == ["hypothesis", "hypothesis"]
    assert rivals[0] == {"id": atom_id("hypothesis", HYP), "text": HYP, "is_null": False}
    assert rivals[1]["is_null"] is True


def test_stitch_ach_cells_become_scored_against_edges():
    corpus, hyp_id, claim_id = _hyp_corpus()
    ev = make_corpus_node(EVIDENCE, type="evidence")
    corpus.nodes[ev.id] = ev
    stitch = StitchOutput(
        ach=[ACHCell(evidence_text=EVIDENCE, hypothesis_text=HYP,
                     consistency="inconsistent"),
             ACHCell(evidence_text="never recorded", hypothesis_text=HYP,
                     consistency="neutral")],
        investigations=[StitchInvestigation(
            farms=["A", "B"], disagreement="Farms disagree on curtailment cause.",
            resolution="Transmission explains part of the curtailment.",
            atoms=[AtomEmission(
                type="claim",
                text="Transmission limits explain part of California solar curtailment.")])],
        declaration_kind="frontier", declaration_summary="Crux-conditional frontier.",
        positions=[BasinPosition(hypothesis_text=HYP, condition="under cost weighting")],
        dissolve=Dissolve())
    result = stitch_harvest(stitch, vantage=make_vantage(farm="stitcher"),
                            corpus=corpus, question_id=Q, ts=TS)
    scored = [e["payload"] for e in result.events
              if e["kind"] == "edge" and e["payload"]["rel"] == "scored_against"]
    assert len(scored) == 1  # exactly one resolved cell
    assert scored[0]["src"] == ev.id and scored[0]["dst"] == hyp_id
    assert scored[0]["consistency"] == "inconsistent"
    assert result.unresolved  # the unrecorded evidence text is reported
    assert len(result.atom_ids) == 1  # investigation atom landed


def test_verify_harvest_upgrades_verified_via_reobservation():
    corpus, hyp_id, claim_id = _hyp_corpus()
    results = [VerificationResult(atom_id=claim_id, verified=True,
                                  evidence="CAISO curtailment reports corroborate the lag.",
                                  source="caiso.com"),
               VerificationResult(atom_id="c-000000000000", verified=True, evidence="x"),
               VerificationResult(atom_id=hyp_id, verified=False, evidence="inconclusive")]
    verifier = make_vantage(farm="verifier", persona="verifier")
    result = verify_harvest(results, corpus=corpus, vantage=verifier, ts=TS)
    assert result.atom_ids == [claim_id]
    assert result.unresolved == [{"atom_id": "c-000000000000"}]
    # replaying the original node + the verification event upgrades verified
    original = node_event(Node.create(type="claim", text=CLAIM, vantage=V,
                                      question_id=Q, ts=TS))
    reduced = reduce_events([original, *result.events])
    assert reduced.nodes[claim_id].verified is True
    assert reduced.nodes[claim_id].sightings == 2
