import json
from pathlib import Path

from antfarm.schema import Edge, Node


def node_event(node: Node) -> dict:
    return {"kind": "node", "payload": node.model_dump()}


def edge_event(edge: Edge) -> dict:
    return {"kind": "edge", "payload": edge.model_dump()}


def status_event(node_id: str, status: str, *, ts: str,
                 died_because: str | None = None) -> dict:
    return {"kind": "status", "payload": {
        "id": node_id, "status": status, "died_because": died_because, "ts": ts}}


def append_events(run_dir: Path, label: str, events: list[dict]) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{label}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return path


def read_events(runs_root: Path) -> list[dict]:
    out: list[dict] = []
    for path in sorted(runs_root.rglob("*.jsonl")):
        with path.open(encoding="utf-8") as f:
            out.extend(json.loads(line) for line in f if line.strip())
    return out
