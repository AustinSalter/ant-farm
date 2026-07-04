from pathlib import Path

from antfarm.graph import answered_challengers
from antfarm.reduce import Corpus

_CHALLENGE_VERB = {"rebuts": "rebutted by", "undercuts": "undercut by"}


def _page(corpus: Corpus, nid: str, answered: set[str]) -> str:
    node = corpus.nodes[nid]
    lines = [
        "---",
        f"type: {node.type}",
        f"status: {node.status}",
        f"verified: {str(node.verified).lower()}",
        f"sightings: {node.sightings}",
        "---",
        "",
        node.text,
        "",
    ]
    outgoing = [e for e in corpus.edges if e.src == nid]
    incoming = [e for e in corpus.edges if e.dst == nid]
    plain = [e for e in outgoing + incoming
             if e.rel not in _CHALLENGE_VERB or e.src == nid]
    if plain:
        lines.append("## Edges")
        for e in plain:
            other = e.dst if e.src == nid else e.src
            entry = f"- {e.rel} → [[{other}]]" if e.src == nid else f"- {e.rel} ← [[{other}]]"
            if e.warrant:
                entry += f" — {e.warrant}"
            lines.append(entry)
        lines.append("")
    challenges = [
        e for e in incoming
        if e.rel in _CHALLENGE_VERB
        and e.src not in answered  # answered challenges are not standing
        and (challenger := corpus.nodes.get(e.src)) is not None
        and challenger.status == "live"
    ]
    if challenges:
        lines.append("## Standing challenges")
        for e in challenges:
            lines.append(f"- {_CHALLENGE_VERB[e.rel]} [[{e.src}]]: {corpus.nodes[e.src].text}")
        lines.append("")
    return "\n".join(lines)


def render_obsidian(corpus: Corpus, view_ids: set[str], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    answered = answered_challengers(corpus)
    paths = []
    for nid in sorted(view_ids):
        path = out_dir / f"{nid}.md"
        path.write_text(_page(corpus, nid, answered), encoding="utf-8")
        paths.append(path)
    return paths
