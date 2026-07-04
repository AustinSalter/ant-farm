import pytest
from pydantic import ValidationError

from antfarm.schema import Edge, Node, atom_id, is_self_contained, normalize_text
from helpers import V, make_node


def test_normalize_collapses_whitespace_and_case():
    assert normalize_text("  Solar  is\ncheaper ") == "solar is cheaper"


def test_atom_id_stable_across_formatting():
    assert atom_id("claim", "Solar is cheaper") == atom_id("claim", "  solar   is CHEAPER ")


def test_atom_id_prefixes_by_type():
    assert atom_id("claim", "x").startswith("c-")
    assert atom_id("evidence", "x").startswith("e-")
    assert atom_id("hypothesis", "x").startswith("h-")
    assert atom_id("tripwire", "x").startswith("w-")


def test_atom_id_differs_by_type():
    assert atom_id("claim", "x") != atom_id("evidence", "x")


def test_self_contained_accepts_standalone_claims():
    assert is_self_contained("Solar LCOE fell roughly 90% between 2010 and 2020.")


def test_self_contained_rejects_unresolved_references():
    assert not is_self_contained("This proves the thesis.")
    assert not is_self_contained("It follows from the above argument.")
    assert not is_self_contained("The former option dominates.")


TEXT = "Solar LCOE fell 90% between 2010 and 2020."


def test_create_computes_content_hash_id():
    n = make_node(TEXT)
    assert n.id.startswith("c-") and len(n.id) == 14
    assert n.id == make_node(TEXT).id  # stable across runs


def test_node_rejects_non_self_contained_text():
    with pytest.raises(ValidationError):
        make_node("This proves the thesis.")


def test_node_rejects_tampered_id():
    n = make_node(TEXT)
    with pytest.raises(ValidationError):
        Node(**{**n.model_dump(), "id": "c-000000000000"})


def test_strength_only_on_evidence():
    with pytest.raises(ValidationError):
        make_node(TEXT, strength=4)  # type=claim
    e = make_node(TEXT, type="evidence", strength=4)
    assert e.strength == 4


def test_node_defaults():
    n = make_node(TEXT)
    assert n.status == "live" and n.verified is False and n.sightings == 1


def test_supports_edge_requires_warrant():
    with pytest.raises(ValidationError):
        Edge(src="e-1", dst="c-1", rel="supports", vantage=V, ts="2026-07-03T00:00:00Z")
    ok = Edge(src="e-1", dst="c-1", rel="supports", warrant="cost curves license the inference",
              vantage=V, ts="2026-07-03T00:00:00Z")
    assert ok.warrant


def test_consistency_only_on_scored_against():
    with pytest.raises(ValidationError):
        Edge(src="e-1", dst="h-1", rel="rebuts", consistency="inconsistent",
             vantage=V, ts="2026-07-03T00:00:00Z")
    ok = Edge(src="e-1", dst="h-1", rel="scored_against", consistency="inconsistent",
              vantage=V, ts="2026-07-03T00:00:00Z")
    assert ok.consistency == "inconsistent"
