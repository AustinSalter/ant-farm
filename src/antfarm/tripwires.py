"""Standing tripwires (spec §5 Phase 0, §8): falsification triggers become
stored sensors; a fired tripwire contests its watched hypotheses and
everything in their depends_on blast radius. The map self-reports staleness."""

from antfarm.emission import TriggerEmission
from antfarm.events import edge_event, node_event, status_event
from antfarm.graph import blast_radius, build_graph
from antfarm.reduce import Corpus
from antfarm.schema import Edge, Node, Vantage


def register_tripwires(triggers: list[TriggerEmission], hypothesis_id: str, *,
                       vantage: Vantage, question_id: str, ts: str) -> list[dict]:
    events: list[dict] = []
    for trigger in triggers:
        if trigger.severity != "high":
            continue
        node = Node.create(type="tripwire", text=trigger.text, vantage=vantage,
                           question_id=question_id, ts=ts)
        events.append(node_event(node))
        events.append(edge_event(Edge(src=hypothesis_id, dst=node.id, rel="depends_on",
                                      vantage=vantage, ts=ts)))
    return events


def standing_tripwires(corpus: Corpus) -> list[dict]:
    out = []
    for nid, node in corpus.nodes.items():
        if node.type != "tripwire" or node.status != "live":
            continue
        watches = [e.src for e in corpus.edges
                   if e.rel == "depends_on" and e.dst == nid]
        # key name matches SentinelCheck.tripwire_id exactly - the sentinel
        # echoes ids from this listing, so the listing must show the same key
        # the report schema demands back.
        out.append({"tripwire_id": nid, "text": node.text, "watches": watches})
    return sorted(out, key=lambda t: str(t["tripwire_id"]))


def fire_tripwire(corpus: Corpus, tripwire_id: str, evidence_text: str, *,
                  vantage: Vantage, question_id: str,
                  ts: str) -> tuple[list[dict], list[str]]:
    watched = [e.src for e in corpus.edges
               if e.rel == "depends_on" and e.dst == tripwire_id
               and e.src in corpus.nodes]
    graph = build_graph(corpus)
    affected: set[str] = set(watched)
    for wid in watched:
        affected |= blast_radius(graph, wid)
    events: list[dict] = []
    evidence = Node.create(type="evidence", text=evidence_text, vantage=vantage,
                           question_id=question_id, ts=ts)
    events.append(node_event(evidence))
    for wid in watched:
        events.append(edge_event(Edge(src=evidence.id, dst=wid, rel="undercuts",
                                      vantage=vantage, ts=ts)))
    for nid in sorted(affected):
        if corpus.nodes[nid].status == "live":
            events.append(status_event(nid, "contested", ts=ts))
    return events, sorted(affected)
