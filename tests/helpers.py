"""Shared test builders. Import these; never re-declare them in a test file."""

from antfarm.reduce import CorpusNode
from antfarm.schema import Edge, Node, Vantage, atom_id

HYPOTHESIS_TEXT = "Storage constraints bind solar growth through 2030."
NULL_TEXT = "No single constraint binds solar growth through 2030."
CLAIM_TEXT = "Grid storage lags panel deployment by several years."
CRITIQUE_TEXT = "Storage-lag statistics conflate contracted and installed capacity."
PREMORTEM_TEXT = "The storage thesis failed by 2027 because interconnection queues cleared."
REBUT_CRITIQUE = "Contracted-capacity inflation is corrected in the dataset revision."
REBUT_PREMORTEM = "Interconnection queue reform bills stalled in every 2025 session."
TRIGGER_TEXT = "A 2027 storage glut with flat solar growth falsifies the storage thesis."


def make_vantage(**overrides) -> Vantage:
    defaults = {"run": "r1", "farm": "A", "family": "claude", "persona": "analyst",
                "round": 1, "sensor": "model"}
    return Vantage(**{**defaults, **overrides})


V = make_vantage()


def make_node(text: str, *, type: str = "claim", vantage: Vantage = V, **kwargs) -> Node:
    return Node.create(type=type, text=text, vantage=vantage,
                       question_id="q-1", ts="2026-07-03T00:00:00Z", **kwargs)


def make_corpus_node(text: str, *, type: str = "claim", **kwargs) -> CorpusNode:
    nid = atom_id(type, text)
    return CorpusNode(id=nid, type=type, text=text, vantage=V, vantages=[V],
                      question_id="q-1", ts="t", **kwargs)


def make_edge(src: str, dst: str, rel: str, **kwargs) -> Edge:
    return Edge(src=src, dst=dst, rel=rel, vantage=V, ts="t", **kwargs)


def framing_fixture() -> dict:
    return {
        "stasis": "quality", "altitude": "market-level, 5-year horizon",
        "dissolve": {"dissolved": False, "diagnosis": None, "replacement_question": None},
        "reference_class": "infrastructure cost-decline theses",
        "base_rate": "roughly half survive a decade",
        "zwicky_dimensions": [{"name": "constraint", "values": ["storage", "grid", "none"]}],
        "incoherent_cells": [],
        "rivals": [{"text": HYPOTHESIS_TEXT, "is_null": False, "warm_started": False},
                   {"text": NULL_TEXT, "is_null": True, "warm_started": False}],
    }


def scout_fixture(round: int, decision: str, **overrides) -> dict:
    base = {
        "sublation": [], "expansion": f"Round {round} expansion of the storage thesis.",
        "atoms": [{"type": "claim", "text": CLAIM_TEXT,
                   "strength": None, "diagnosticity": None}],
        "edges": [],
        "falsification_triggers": [],
        "compressed_state": f"Thesis after round {round}: storage binds growth.",
        "confidence_r": "med", "confidence_c": "med",
        "ledger_entry": None, "decision": decision, "died_because": None,
    }
    if round >= 2:
        base["sublation"] = [
            {"critique": CRITIQUE_TEXT, "disposition": "rebutted",
             "response": REBUT_CRITIQUE}]
        base["atoms"] = [{"type": "claim", "text": REBUT_CRITIQUE,
                          "strength": None, "diagnosticity": None}]
        base["edges"] = [{"src": REBUT_CRITIQUE, "dst": CRITIQUE_TEXT,
                          "rel": "rebuts", "warrant": None}]
        base["falsification_triggers"] = [{"text": TRIGGER_TEXT, "severity": "high"}]
        base["ledger_entry"] = {"trigger": "round 1 critique",
                                "change": "rebutted warrant probe",
                                "novel_content": True}
    return {**base, **overrides}


def critique_fixture() -> dict:
    return {
        "findings": [{"target_text": CLAIM_TEXT, "kind": "warrant_probe",
                      "classification": "undercutting", "severity": "high",
                      "text": CRITIQUE_TEXT}],
        "premortem": "The hypothesis could be overturned by unforeseen market changes.",
        "summary": "One HIGH warrant probe.",
    }
