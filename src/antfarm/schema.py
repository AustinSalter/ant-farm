import hashlib
import re
from typing import Literal

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
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def atom_id(node_type: str, text: str) -> str:
    digest = hashlib.sha256(f"{node_type}:{normalize_text(text)}".encode()).hexdigest()
    return f"{ID_PREFIX[node_type]}-{digest[:12]}"


# "that" is deliberately absent: "That solar is cheap is well documented" is self-contained
_UNRESOLVED = re.compile(
    r"^(it|this|they|these|those|he|she)\b"
    r"|\b(the above|the former|the latter|as mentioned|as noted)\b",
    re.IGNORECASE,
)


def is_self_contained(text: str) -> bool:
    return _UNRESOLVED.search(text.strip()) is None
