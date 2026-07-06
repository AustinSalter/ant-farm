from antfarm.emission import TriggerEmission
from antfarm.events import node_event
from antfarm.reduce import Corpus, reduce_events
from antfarm.schema import Node
from antfarm.tripwires import fire_tripwire, register_tripwires, standing_tripwires
from helpers import make_corpus_node, make_edge, make_vantage

V = make_vantage(farm="A")
TS = "2026-07-04T00:00:00Z"
TRIGGER = TriggerEmission(
    text="A 2027 storage glut with flat solar growth falsifies the storage thesis.",
    severity="high")


def _corpus_with_hypothesis():
    hyp = make_corpus_node("Storage constraints bind solar growth through 2030.",
                           type="hypothesis")
    dependent = make_corpus_node("Solar installers should hedge storage exposure.")
    corpus = Corpus(nodes={hyp.id: hyp, dependent.id: dependent},
                    edges=[make_edge(dependent.id, hyp.id, "depends_on")])
    return corpus, hyp.id, dependent.id


def test_register_emits_tripwire_watching_hypothesis_high_only():
    corpus, hyp_id, _ = _corpus_with_hypothesis()
    low = TriggerEmission(text="A mild dip would be surprising.", severity="low")
    events = register_tripwires([TRIGGER, low], hyp_id, vantage=V,
                                question_id="q-1", ts=TS)
    assert [e["kind"] for e in events] == ["node", "edge"]
    assert events[0]["payload"]["type"] == "tripwire"
    edge = events[1]["payload"]
    assert edge["src"] == hyp_id and edge["rel"] == "depends_on"


def test_standing_tripwires_lists_live_with_watches():
    corpus, hyp_id, _ = _corpus_with_hypothesis()
    events = [node_event(Node.model_validate(n.model_dump()))
              for n in corpus.nodes.values()]
    events += [{"kind": "edge", "payload": e.model_dump()} for e in corpus.edges]
    events += register_tripwires([TRIGGER], hyp_id, vantage=V, question_id="q-1", ts=TS)
    reduced = reduce_events(events)
    standing = standing_tripwires(reduced)
    assert len(standing) == 1
    assert standing[0]["watches"] == [hyp_id]


def test_fire_contests_watched_and_blast_radius():
    corpus, hyp_id, dep_id = _corpus_with_hypothesis()
    reg = register_tripwires([TRIGGER], hyp_id, vantage=V, question_id="q-1", ts=TS)
    events = [node_event(Node.model_validate(n.model_dump()))
              for n in corpus.nodes.values()]
    events += [{"kind": "edge", "payload": e.model_dump()} for e in corpus.edges]
    events += reg
    reduced = reduce_events(events)
    trip_id = reg[0]["payload"]["id"]

    fire_events, affected = fire_tripwire(
        reduced, trip_id, "A storage glut arrived in 2027 while solar growth was flat.",
        vantage=make_vantage(farm="sentinel"), question_id="q-1", ts=TS)
    assert affected == sorted([hyp_id, dep_id])
    final = reduce_events(events + fire_events)
    assert final.nodes[hyp_id].status == "contested"
    assert final.nodes[dep_id].status == "contested"
    undercuts = [e for e in final.edges if e.rel == "undercuts"]
    assert len(undercuts) == 1 and undercuts[0].dst == hyp_id
