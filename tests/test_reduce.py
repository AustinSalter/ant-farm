import pytest

from antfarm.events import edge_event, node_event, status_event
from antfarm.reduce import reduce_events
from antfarm.schema import Edge
from helpers import V, make_node, make_vantage

V2 = make_vantage(farm="B", family="gpt", persona="skeptic")


def test_new_node_enters_with_one_vantage():
    n = make_node("Grid storage is the binding constraint on solar buildout.")
    corpus = reduce_events([node_event(n)])
    cn = corpus.nodes[n.id]
    assert cn.sightings == 1 and cn.vantages == [V]


def test_refound_node_is_observation_not_duplicate():
    a = make_node("Grid storage is the binding constraint on solar buildout.")
    b = make_node("Grid storage is the binding constraint on solar buildout.",
                  vantage=V2, verified=True)
    corpus = reduce_events([node_event(a), node_event(b)])
    assert len(corpus.nodes) == 1
    cn = corpus.nodes[a.id]
    assert cn.sightings == 2
    assert cn.vantages == [V, V2]
    assert cn.verified is True  # verification upgrades, never downgrades


def test_observation_upgrades_strength_and_diagnosticity():
    a = make_node("Battery cost curves bound solar deployment.", type="evidence",
                  strength=2, diagnosticity="med")
    b = make_node("Battery cost curves bound solar deployment.", type="evidence",
                  vantage=V2, strength=4, diagnosticity="high")
    corpus = reduce_events([node_event(a), node_event(b)])
    cn = corpus.nodes[a.id]
    assert cn.strength == 4 and cn.diagnosticity == "high"


def test_supersedes_edge_marks_old_node_without_deletion():
    old = make_node("Coal plants retire on a 40-year schedule.")
    new = make_node("Coal plants retire on a 30-year schedule after IRA incentives.")
    sup = Edge(src=new.id, dst=old.id, rel="supersedes", vantage=V, ts="t")
    corpus = reduce_events([node_event(old), node_event(new), edge_event(sup)])
    assert corpus.nodes[old.id].status == "superseded"
    assert corpus.nodes[old.id].superseded_by == new.id
    assert old.id in corpus.nodes  # never deleted


def test_supersedes_arriving_before_its_target_still_applies():
    # cross-file replay order can deliver the edge before the node (spec: append-only,
    # order-tolerant fold) - the reducer must defer and re-apply, never silently drop
    old = make_node("Coal plants retire on a 40-year schedule.")
    new = make_node("Coal plants retire on a 30-year schedule after IRA incentives.")
    sup = Edge(src=new.id, dst=old.id, rel="supersedes", vantage=V, ts="t")
    corpus = reduce_events([edge_event(sup), node_event(old), node_event(new)])
    assert corpus.nodes[old.id].status == "superseded"
    assert corpus.nodes[old.id].superseded_by == new.id


def test_conceded_stays_on_map_with_died_because():
    h = make_node("Fusion arrives before 2035 at grid scale.")
    corpus = reduce_events([
        node_event(h),
        status_event(h.id, "conceded", ts="t", died_because="no surviving evidence path"),
    ])
    assert corpus.nodes[h.id].status == "conceded"
    assert corpus.nodes[h.id].died_because == "no surviving evidence path"


def test_unknown_event_kind_raises():
    with pytest.raises(ValueError, match="unknown event kind"):
        reduce_events([{"kind": "telemetry", "payload": {}}])


def test_deferred_event_with_missing_target_raises():
    with pytest.raises(ValueError, match="unknown node"):
        reduce_events([status_event("h-000000000099", "conceded", ts="t")])


def test_deferred_supersedes_with_missing_target_raises():
    src = make_node("Coal plants retire on a 30-year schedule after IRA incentives.")
    sup = Edge(src=src.id, dst="h-000000000099", rel="supersedes", vantage=V, ts="t")
    with pytest.raises(ValueError, match="unknown node"):
        reduce_events([edge_event(sup)])
