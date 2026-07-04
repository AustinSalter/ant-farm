from antfarm.reduce import Corpus
from antfarm.render import render_obsidian
from helpers import make_corpus_node, make_edge


def test_render_pages_edges_and_standing_challenges(tmp_path):
    a = make_corpus_node("Grid storage capacity limits solar deployment growth.",
                         verified=True)
    e = make_corpus_node("Battery production doubled between 2023 and 2025.",
                         type="evidence", verified=True)
    u = make_corpus_node("Deployment statistics conflate contracted and installed capacity.")
    dead = make_corpus_node("Battery production numbers are vendor-inflated projections.")
    corpus = Corpus(nodes={n.id: n for n in (a, e, u, dead)}, edges=[
        make_edge(e.id, a.id, "supports", warrant="production growth bounds deployment"),
        make_edge(u.id, a.id, "undercuts"),
        make_edge(dead.id, a.id, "undercuts"),
        make_edge(e.id, dead.id, "rebuts"),  # dead's challenge has been answered
    ])
    view_ids = {a.id, e.id}  # challengers are well-only

    paths = render_obsidian(corpus, view_ids, tmp_path)
    assert sorted(p.name for p in paths) == sorted(f"{nid}.md" for nid in view_ids)

    page = (tmp_path / f"{a.id}.md").read_text()
    assert "status: live" in page and "verified: true" in page
    assert a.text in page
    assert f"[[{e.id}]]" in page and "production growth bounds deployment" in page
    # standing challenge from a non-view node still appears (one edge away, spec 4.3)
    assert f"undercut by [[{u.id}]]" in page
    assert u.text in page
    # an answered challenge is not standing and must not render
    assert dead.id not in page
