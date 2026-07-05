import json

from antfarm.brief import probe, stitch_brief, verification_queue, warm_brief
from antfarm.cluster import cosine  # noqa: F401
from antfarm.farm import FarmMeta, append_turns, init_farm, write_outcome
from antfarm.reduce import Corpus
from antfarm.transcript import Turn
from helpers import make_corpus_node, make_vantage


def _seeded_corpus():
    view_claim = make_corpus_node("Storage capacity limits solar deployment growth.",
                                  verified=True)
    crux = make_corpus_node("Whether curtailment reflects storage or transmission.",
                            status="contested")
    dead = make_corpus_node("Fusion arrives before 2035 at grid scale.",
                            type="hypothesis", status="conceded",
                            died_because="no deployment evidence")
    return Corpus(nodes={n.id: n for n in (view_claim, crux, dead)}), view_claim, crux, dead


def test_warm_brief_carries_view_cruxes_conceded_and_declaration(tmp_path):
    corpus, view_claim, crux, dead = _seeded_corpus()
    run_dir = tmp_path / "r0001"
    run_dir.mkdir()
    (run_dir / "declaration.json").write_text(json.dumps({"kind": "basin"}))
    brief = warm_brief(corpus, "q-1", tmp_path)
    assert brief["view"][0]["id"] == view_claim.id
    assert brief["cruxes"][0]["id"] == crux.id
    assert brief["conceded"] == [{"text": dead.text,
                                  "died_because": "no deployment evidence"}]
    assert brief["declaration"] == {"kind": "basin"}


def test_stitch_brief_reads_farm_dirs_and_inventories(tmp_path):
    corpus, *_ = _seeded_corpus()
    ev = make_corpus_node("California curtailed 2.4 TWh of solar in 2024.",
                          type="evidence", strength=4, verified=True)
    corpus.nodes[ev.id] = ev
    meta = FarmMeta(farm="A", hypothesis_id="h-000000000001",
                    hypothesis_text="Storage binds growth.", persona="p",
                    family="opus", question_id="q-1", question_text="q")
    d = init_farm(tmp_path, "r0001", "A", meta)
    append_turns(d, [Turn(turn=1, role="assistant", phase="compress", iteration=1,
                          content="final state")])
    write_outcome(d, "CONCLUDE", None)
    brief = stitch_brief(corpus, tmp_path, "r0001")
    assert brief["farms"][0]["compressed_state"] == "final state"
    assert brief["farms"][0]["outcome"]["decision"] == "CONCLUDE"
    assert any(e["id"] == ev.id for e in brief["evidence"])
    assert any(h["status"] == "conceded" for h in brief["hypotheses"])


def test_verification_queue_flags_late_singletons_first():
    # make_corpus_node stamps helpers.V (round 1); rebuild `late` at round 3
    early = make_corpus_node("Early-round unverified claim about panel costs.")
    late = make_corpus_node("Late-round novel claim about interconnection queues.")
    late = late.model_copy(update={"vantage": make_vantage(round=3),
                                   "vantages": [make_vantage(round=3)]})
    verified = make_corpus_node("Already verified claim.", verified=True)
    corpus = Corpus(nodes={n.id: n for n in (early, late, verified)})
    queue = verification_queue(corpus)
    assert [q["id"] for q in queue] == [late.id, early.id]
    assert queue[0]["late"] is True and queue[1]["late"] is False


def test_probe_flags_duplicate_and_novel(tmp_path):
    corpus, view_claim, _, dead = _seeded_corpus()

    def fake_embed(texts):
        def vec(t):
            low = t.lower()
            if "storage" in low:
                return [1.0, 0.0, 0.0]
            if "fusion" in low:
                return [0.0, 1.0, 0.0]
            return [0.0, 0.0, 1.0]
        return [vec(t) for t in texts]

    dup = probe(corpus, fake_embed, "STORAGE capacity limits things.")
    assert dup["novel"] is False and dup["nearest"][0]["score"] == 1.0
    # a candidate matching an existing HYPOTHESIS is not a hole either
    hypo_dup = probe(corpus, fake_embed, "Fusion at grid scale lands soon.")
    assert hypo_dup["novel"] is False and hypo_dup["nearest"][0]["id"] == dead.id
    novel = probe(corpus, fake_embed, "Nobody has considered permitting reform.")
    assert novel["novel"] is True


def test_probe_on_empty_corpus_is_novel():
    assert probe(Corpus(), lambda ts: [[1.0]] * len(ts), "anything") == {
        "novel": True, "nearest": []}
