from antfarm.events import append_events, edge_event, node_event, read_events, status_event
from antfarm.schema import Edge
from helpers import V, make_node


def test_roundtrip_and_append_only(tmp_path):
    run_dir = tmp_path / "r0001"
    n = make_node("Solar LCOE fell 90% between 2010 and 2020.")
    e = Edge(src=n.id, dst="h-000000000001", rel="rebuts", vantage=V, ts="2026-07-03T00:00:00Z")

    append_events(run_dir, "p2-farmA-r01", [node_event(n)])
    append_events(run_dir, "p2-farmA-r01", [edge_event(e)])  # second append accumulates

    events = read_events(tmp_path)
    assert [ev["kind"] for ev in events] == ["node", "edge"]
    assert events[0]["payload"]["id"] == n.id


def test_replay_order_is_sorted_path_order(tmp_path):
    append_events(tmp_path / "r0001", "p2-farmB-r01", [status_event("h-1", "contested", ts="t")])
    append_events(tmp_path / "r0001", "p1-framing", [status_event("h-1", "live", ts="t")])
    kinds = [ev["payload"]["status"] for ev in read_events(tmp_path)]
    assert kinds == ["live", "contested"]  # p1 file replays before p2 file


def test_status_event_carries_died_because():
    ev = status_event("h-1", "conceded", ts="t", died_because="failed severity gate")
    assert ev == {"kind": "status", "payload": {
        "id": "h-1", "status": "conceded", "died_because": "failed severity gate", "ts": "t"}}
