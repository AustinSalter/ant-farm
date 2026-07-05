import pytest
from pydantic import ValidationError

from antfarm.emission import (
    AtomEmission,
    Dissolve,
    EdgeEmission,
    FramingOutput,
    RivalHypothesis,
    ScoutRoundOutput,
    export_schemas,
)

SCOUT_KW = {
    "expansion": "Grid storage constrains solar buildout because batteries lag panels.",
    "atoms": [AtomEmission(type="claim", text="Grid storage lags panel deployment by years.")],
    "compressed_state": "Thesis: storage, not panels, is the binding constraint.",
    "confidence_r": "med",
    "confidence_c": "high",
}


def test_atom_emission_has_no_provenance_fields():
    fields = set(AtomEmission.model_fields)
    assert fields == {"type", "text", "strength", "diagnosticity"}
    # no id, no vantage, no ts, no verified - the orchestrator stamps those


def test_atom_emission_rejects_crux_and_tripwire_types():
    with pytest.raises(ValidationError):
        AtomEmission(type="crux", text="x")  # cruxes are computed, never emitted
    with pytest.raises(ValidationError):
        AtomEmission(type="tripwire", text="x")  # tripwires come from triggers


def test_supports_edge_requires_warrant_at_emission():
    with pytest.raises(ValidationError):
        EdgeEmission(src="a", dst="b", rel="supports")
    ok = EdgeEmission(src="a", dst="b", rel="supports", warrant="cost curves license this")
    assert ok.warrant


def test_edge_emission_excludes_scored_against():
    with pytest.raises(ValidationError):
        EdgeEmission(src="a", dst="b", rel="scored_against")  # stitcher ACH cells only


def test_scout_round_decision_literals():
    out = ScoutRoundOutput(decision="CONTINUE", **SCOUT_KW)
    assert out.decision == "CONTINUE"
    with pytest.raises(ValidationError):
        ScoutRoundOutput(decision="HALT", **SCOUT_KW)


def test_concede_requires_died_because():
    with pytest.raises(ValidationError):
        ScoutRoundOutput(decision="CONCEDE", **SCOUT_KW)
    ok = ScoutRoundOutput(decision="CONCEDE", died_because="rival explains the evidence",
                          **SCOUT_KW)
    assert ok.died_because


def test_dissolve_requires_replacement_question():
    with pytest.raises(ValidationError):
        Dissolve(dissolved=True, diagnosis="fake binary")
    ok = Dissolve(dissolved=True, diagnosis="fake binary",
                  replacement_question="Which storage mix serves peak load cheapest?")
    assert ok.replacement_question


FRAMING_KW = {
    "stasis": "quality",
    "altitude": "market-level, 5-year horizon",
    "reference_class": "infrastructure cost-decline theses",
    "base_rate": "roughly half of such theses survive a decade",
    "zwicky_dimensions": [],
    "incoherent_cells": [],
}


def test_framing_requires_rivals_with_null():
    with pytest.raises(ValidationError, match="2-4 rival"):
        FramingOutput(dissolve=Dissolve(), rivals=[RivalHypothesis(text="only one")],
                      **FRAMING_KW)
    with pytest.raises(ValidationError, match="null"):
        FramingOutput(dissolve=Dissolve(),
                      rivals=[RivalHypothesis(text="a"), RivalHypothesis(text="b")],
                      **FRAMING_KW)
    ok = FramingOutput(dissolve=Dissolve(), rivals=[
        RivalHypothesis(text="Storage is the binding constraint."),
        RivalHypothesis(text="No single constraint dominates.", is_null=True),
    ], **FRAMING_KW)
    assert len(ok.rivals) == 2


def test_dissolved_framing_needs_no_rivals():
    ok = FramingOutput(
        dissolve=Dissolve(dissolved=True, diagnosis="presupposes a single constraint",
                          replacement_question="What limits solar in each region?"),
        rivals=[], **FRAMING_KW)
    assert ok.dissolve.dissolved


def test_export_schemas_covers_every_agent_output():
    schemas = export_schemas()
    assert set(schemas) == {
        "scout_round", "critique_report", "framing", "hole_finder", "stitch",
        "sentinel_report", "verification_result", "persona_swap", "curator",
        "atom_batch",
    }
    assert schemas["scout_round"]["properties"]["decision"]["enum"] == [
        "CONTINUE", "CONCLUDE", "ELEVATE", "CONCEDE"]
