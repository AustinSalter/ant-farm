import hashlib
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

NodeType = Literal[
    "claim", "evidence", "tension", "crux", "hypothesis", "source", "vantage", "tripwire"
]
NodeStatus = Literal["live", "contested", "superseded", "conceded"]
EdgeRel = Literal[
    "supports", "rebuts", "undercuts", "qualifies",
    "bridges", "depends_on", "supersedes", "scored_against",
]

ID_PREFIX: dict[str, str] = {
    "claim": "c", "evidence": "e", "tension": "t", "crux": "x",
    "hypothesis": "h", "source": "s", "vantage": "v", "tripwire": "w",
    # not a NodeType: question ids share the content-hash scheme (cli.py) but
    # questions are never corpus nodes.
    "question": "q",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def atom_id(node_type: str, text: str) -> str:
    digest = hashlib.sha256(f"{node_type}:{normalize_text(text)}".encode()).hexdigest()
    return f"{ID_PREFIX[node_type]}-{digest[:12]}"


# Bare "that" is deliberately absent from the leading-pronoun alternation below:
# "That solar is cheap is well documented" opens a nominal clause ("that" + noun
# phrase), which is self-contained. But "that" is also a demonstrative pronoun
# subject ("That proves the thesis"), structurally identical to "this"/"it", which
# must be rejected. We only catch the demonstrative case: a leading "that"
# immediately followed by a verb rather than a noun phrase.
_UNRESOLVED = re.compile(
    r"^(it|this|they|these|those|he|she)\b"
    r"|\b(the above|the former|the latter|as mentioned|as noted)\b"
    r"|^that\s+(?:proves|shows|means|implies|explains|follows|demonstrates|confirms|"
    r"suggests|contradicts|settles|is|was|does|did|would|will|can|cannot|won't|doesn't)\b",
    re.IGNORECASE,
)


def is_self_contained(text: str) -> bool:
    return _UNRESOLVED.search(text.strip()) is None


class Vantage(BaseModel):
    run: str
    farm: str
    family: str
    persona: str
    round: int
    sensor: Literal["model", "human"]


class Node(BaseModel):
    id: str
    type: NodeType
    text: str
    vantage: Vantage
    status: NodeStatus = "live"
    superseded_by: str | None = None
    strength: int | None = Field(default=None, ge=1, le=5)
    diagnosticity: Literal["high", "med", "none"] | None = None
    verified: bool = False
    sightings: int = 1
    question_id: str
    ts: str

    @field_validator("text")
    @classmethod
    def _text_self_contained(cls, v: str) -> str:
        if not is_self_contained(v):
            raise ValueError(f"atom text is not self-contained: {v[:60]!r}")
        return v

    @model_validator(mode="after")
    def _invariants(self) -> "Node":
        if self.id != atom_id(self.type, self.text):
            raise ValueError("id does not match content hash of (type, text)")
        if self.strength is not None and self.type != "evidence":
            raise ValueError("strength applies to evidence nodes only")
        return self

    @classmethod
    def create(cls, *, type: NodeType, text: str, vantage: Vantage,
               question_id: str, ts: str, **kwargs: Any) -> "Node":
        return cls(id=atom_id(type, text), type=type, text=text, vantage=vantage,
                   question_id=question_id, ts=ts, **kwargs)


class Edge(BaseModel):
    src: str
    dst: str
    rel: EdgeRel
    warrant: str | None = None
    consistency: Literal["consistent", "inconsistent", "neutral"] | None = None
    vantage: Vantage
    ts: str

    @model_validator(mode="after")
    def _invariants(self) -> "Edge":
        if self.rel == "supports" and not self.warrant:
            raise ValueError("supports edges require a warrant (Toulmin, spec §4.1)")
        if self.consistency is not None and self.rel != "scored_against":
            raise ValueError("consistency applies to scored_against edges only")
        return self
