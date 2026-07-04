"""Shared test builders. Import these; never re-declare them in a test file."""

from antfarm.schema import Node, Vantage


def make_vantage(**overrides) -> Vantage:
    defaults = {"run": "r1", "farm": "A", "family": "claude", "persona": "analyst",
                "round": 1, "sensor": "model"}
    return Vantage(**{**defaults, **overrides})


V = make_vantage()


def make_node(text: str, *, type: str = "claim", vantage: Vantage = V, **kwargs) -> Node:
    return Node.create(type=type, text=text, vantage=vantage,
                       question_id="q-1", ts="2026-07-03T00:00:00Z", **kwargs)
