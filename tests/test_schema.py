from antfarm.schema import atom_id, is_self_contained, normalize_text


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
