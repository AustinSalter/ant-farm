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


class _StubMatcher:
    """Fake matcher: merges the node whose id is a key of `merges` into the mapped
    target id, provided that target is already present in the corpus."""

    def __init__(self, merges: dict[str, str]):
        self.merges = merges

    def find_match(self, node, nodes):  # noqa: ANN001, ANN201 - test stub
        target = self.merges.get(node.id)
        return target if target in nodes else None


def test_supersedes_edge_targeting_merged_away_id_resolves_to_canonical():
    # b merges into a (paraphrase); a later supersedes edge naming b.id as its
    # target must still land on the canonical node a, not dangle/raise.
    a = make_node("Grid storage is the binding constraint on solar buildout.")
    b = make_node("Storage capacity, not panel cost, now limits solar deployment.")
    new = make_node("Coal plants retire on a 30-year schedule after IRA incentives.")
    matcher = _StubMatcher({b.id: a.id})
    sup = Edge(src=new.id, dst=b.id, rel="supersedes", vantage=V, ts="t")
    corpus = reduce_events(
        [node_event(a), node_event(b), node_event(new), edge_event(sup)],
        matcher=matcher)
    assert b.id not in corpus.nodes
    assert corpus.nodes[a.id].status == "superseded"
    assert corpus.nodes[a.id].superseded_by == new.id


def test_status_event_targeting_merged_away_id_applies_to_canonical():
    a = make_node("Grid storage is the binding constraint on solar buildout.")
    b = make_node("Storage capacity, not panel cost, now limits solar deployment.")
    matcher = _StubMatcher({b.id: a.id})
    corpus = reduce_events([
        node_event(a), node_event(b),
        status_event(b.id, "conceded", ts="t", died_because="superseded by merge"),
    ], matcher=matcher)
    assert corpus.nodes[a.id].status == "conceded"
    assert corpus.nodes[a.id].died_because == "superseded by merge"


def test_edge_dst_targeting_merged_away_id_rewritten_to_canonical():
    # A plain (non-supersedes) edge naming the merged-away id must have its dst
    # rewritten so build_graph doesn't silently drop it.
    a = make_node("Grid storage is the binding constraint on solar buildout.")
    b = make_node("Storage capacity, not panel cost, now limits solar deployment.")
    new = make_node("Coal plants retire on a 30-year schedule after IRA incentives.")
    matcher = _StubMatcher({b.id: a.id})
    rebut = Edge(src=new.id, dst=b.id, rel="rebuts", vantage=V, ts="t")
    corpus = reduce_events(
        [node_event(a), node_event(b), node_event(new), edge_event(rebut)],
        matcher=matcher)
    assert corpus.edges[-1].dst == a.id


def test_edge_arriving_before_merge_establishing_node_is_still_rewritten():
    # The rebuts edge names b.id BEFORE the node event for b arrives (which is
    # what establishes the alias b -> a). Stored edges must be re-resolved once
    # the fold completes and the alias map is final.
    a = make_node("Grid storage is the binding constraint on solar buildout.")
    b = make_node("Storage capacity, not panel cost, now limits solar deployment.")
    new = make_node("Coal plants retire on a 30-year schedule after IRA incentives.")
    matcher = _StubMatcher({b.id: a.id})
    rebut = Edge(src=new.id, dst=b.id, rel="rebuts", vantage=V, ts="t")
    corpus = reduce_events(
        [node_event(a), node_event(new), edge_event(rebut), node_event(b)],
        matcher=matcher)
    assert corpus.edges[-1].dst == a.id


def test_events_referencing_genuinely_unknown_id_still_raise_with_matcher():
    a = make_node("Grid storage is the binding constraint on solar buildout.")
    matcher = _StubMatcher({})
    with pytest.raises(ValueError, match="unknown node"):
        reduce_events([
            node_event(a),
            status_event("h-000000000099", "conceded", ts="t"),
        ], matcher=matcher)


def test_supersede_src_resolved_after_later_merge_establishing_its_alias():
    # The supersedes edge applies immediately (old already exists), but its src
    # (b.id) hasn't merged into a yet. old.superseded_by must not dangle to the
    # merged-away id once b's merge into a is processed later in the fold.
    old = make_node("Coal plants retire on a 40-year schedule.")
    a = make_node("Grid storage is the binding constraint on solar buildout.")
    b = make_node("Storage capacity, not panel cost, now limits solar deployment.")
    matcher = _StubMatcher({b.id: a.id})
    sup = Edge(src=b.id, dst=old.id, rel="supersedes", vantage=V, ts="t")
    corpus = reduce_events(
        [node_event(old), node_event(a), edge_event(sup), node_event(b)],
        matcher=matcher)
    assert corpus.nodes[old.id].superseded_by == a.id


def test_invalid_status_raises():
    n = make_node("Fusion arrives before 2035 at grid scale.")
    with pytest.raises(ValueError, match="unknown status"):
        reduce_events([node_event(n), status_event(n.id, "concieved", ts="t")])


def test_died_because_clears_on_revival_to_live():
    h = make_node("Fusion arrives before 2035 at grid scale.")
    corpus = reduce_events([
        node_event(h),
        status_event(h.id, "conceded", ts="t1", died_because="no surviving evidence path"),
        status_event(h.id, "live", ts="t2"),
    ])
    assert corpus.nodes[h.id].status == "live"
    assert corpus.nodes[h.id].died_because is None


def test_hypothesis_nodes_never_merge_via_matcher():
    # rivals on one question routinely embed above the entailment threshold;
    # a matcher merge would alias one rival onto another, so hypothesis
    # identity is the exact content hash only
    a = make_node("Storage constraints bind solar growth through 2030.",
                  type="hypothesis")
    b = make_node("Interconnection queues bind solar growth through 2030.",
                  type="hypothesis")
    matcher = _StubMatcher({b.id: a.id})
    corpus = reduce_events([node_event(a), node_event(b)], matcher=matcher)
    assert a.id in corpus.nodes and b.id in corpus.nodes
    assert corpus.nodes[b.id].sightings == 1


def test_identical_hypothesis_text_still_reobserves_by_exact_id():
    a = make_node("Storage constraints bind solar growth through 2030.",
                  type="hypothesis")
    again = make_node("Storage constraints bind solar growth through 2030.",
                      type="hypothesis", vantage=V2)
    corpus = reduce_events([node_event(a), node_event(again)],
                           matcher=_StubMatcher({}))
    assert len(corpus.nodes) == 1
    assert corpus.nodes[a.id].sightings == 2
