"""Agent-facing output models. Everything a survey agent returns is one of these,
schema-forced at the agent() call via export_schemas(). Emissions carry no id,
no vantage, no ts, no verified flag - antfarm.harvest stamps provenance."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from antfarm.transcript import LedgerEntry

Band = Literal["low", "med", "high"]
Severity = Literal["low", "med", "high"]
FarmDecision = Literal["CONTINUE", "CONCLUDE", "ELEVATE", "CONCEDE"]
EmittableType = Literal["claim", "evidence", "tension", "hypothesis", "source"]
EmittableRel = Literal[
    "supports", "rebuts", "undercuts", "qualifies", "bridges", "depends_on", "supersedes"
]


class AtomEmission(BaseModel):
    type: EmittableType
    text: str
    strength: int | None = Field(default=None, ge=1, le=5)
    diagnosticity: Literal["high", "med", "none"] | None = None


class EdgeEmission(BaseModel):
    """Endpoints are either an existing corpus id (c-8f3a...) or the exact text
    of an atom in the same emission batch."""

    src: str
    dst: str
    rel: EmittableRel
    warrant: str | None = None

    @model_validator(mode="after")
    def _supports_needs_warrant(self) -> "EdgeEmission":
        if self.rel == "supports" and not self.warrant:
            raise ValueError("supports edges require a warrant (Toulmin, spec §4.1)")
        return self


class AtomBatch(BaseModel):
    atoms: list[AtomEmission]
    edges: list[EdgeEmission] = Field(default_factory=list)


class TriggerEmission(BaseModel):
    """A falsification trigger: a self-contained condition that would falsify
    the farm's thesis, graded by severity (Popper/Mayo, spec §7)."""

    text: str
    severity: Severity


class SublationItem(BaseModel):
    critique: str
    disposition: Literal["accepted", "rebutted", "qualified"]
    response: str


class ScoutRoundOutput(BaseModel):
    sublation: list[SublationItem] = Field(default_factory=list)
    expansion: str
    atoms: list[AtomEmission]
    edges: list[EdgeEmission] = Field(default_factory=list)
    falsification_triggers: list[TriggerEmission] = Field(default_factory=list)
    compressed_state: str
    confidence_r: Band
    confidence_c: Band
    ledger_entry: LedgerEntry | None = None
    decision: FarmDecision
    died_because: str | None = None

    @model_validator(mode="after")
    def _concede_needs_died_because(self) -> "ScoutRoundOutput":
        if self.decision == "CONCEDE" and not self.died_because:
            raise ValueError("CONCEDE requires died_because")
        return self


class CritiqueFinding(BaseModel):
    target_text: str
    kind: Literal["warrant_probe", "premortem", "contradiction", "evidence_challenge"]
    classification: Literal["rebutting", "undercutting"]
    severity: Severity
    text: str


class CritiqueReport(BaseModel):
    findings: list[CritiqueFinding]
    premortem: str
    summary: str


class Dissolve(BaseModel):
    dissolved: bool = False
    diagnosis: str | None = None
    replacement_question: str | None = None

    @model_validator(mode="after")
    def _dissolved_needs_replacement(self) -> "Dissolve":
        if self.dissolved and not self.replacement_question:
            raise ValueError("DISSOLVE requires a replacement question (spec §5 Phase 1)")
        return self


class ZwickyDimension(BaseModel):
    name: str
    values: list[str]


class ZwickyCell(BaseModel):
    assignment: dict[str, str]
    reason: str


class RivalHypothesis(BaseModel):
    text: str
    is_null: bool = False
    warm_started: bool = False


class FramingOutput(BaseModel):
    stasis: Literal["fact", "definition", "quality", "policy"]
    altitude: str
    dissolve: Dissolve
    reference_class: str
    base_rate: str
    zwicky_dimensions: list[ZwickyDimension]
    incoherent_cells: list[ZwickyCell] = Field(default_factory=list)
    rivals: list[RivalHypothesis] = Field(default_factory=list)

    @model_validator(mode="after")
    def _rivals_unless_dissolved(self) -> "FramingOutput":
        if self.dissolve.dissolved:
            return self
        if not 2 <= len(self.rivals) <= 4:
            raise ValueError("framing requires 2-4 rival hypotheses (spec §5 Phase 1)")
        if not any(r.is_null for r in self.rivals):
            raise ValueError("rivals must include the null hypothesis")
        return self


class HoleFinderOutput(BaseModel):
    candidate: str | None
    reasoning: str


class ACHCell(BaseModel):
    evidence_text: str
    hypothesis_text: str
    consistency: Literal["consistent", "inconsistent", "neutral"]


class StitchInvestigation(BaseModel):
    farms: list[str]
    disagreement: str
    resolution: str
    atoms: list[AtomEmission] = Field(default_factory=list)
    edges: list[EdgeEmission] = Field(default_factory=list)


class BasinPosition(BaseModel):
    hypothesis_text: str
    condition: str | None = None


class StitchOutput(BaseModel):
    ach: list[ACHCell]
    investigations: list[StitchInvestigation] = Field(default_factory=list)
    declaration_kind: Literal["basin", "frontier"]
    declaration_summary: str
    positions: list[BasinPosition]
    dissolve: Dissolve


class SentinelCheck(BaseModel):
    tripwire_id: str
    fired: bool
    evidence: str


class SentinelReport(BaseModel):
    checks: list[SentinelCheck]


class VerificationResult(BaseModel):
    atom_id: str
    verified: bool
    evidence: str
    source: str | None = None


class RegeneratedTurn(BaseModel):
    phase: Literal["sublate", "expand", "compress"]
    iteration: int
    content: str


class PersonaSwapOutput(BaseModel):
    turns: list[RegeneratedTurn]


class CuratorOutput(BaseModel):
    map_markdown: str


SCHEMAS: dict[str, type[BaseModel]] = {
    "scout_round": ScoutRoundOutput,
    "critique_report": CritiqueReport,
    "framing": FramingOutput,
    "hole_finder": HoleFinderOutput,
    "stitch": StitchOutput,
    "sentinel_report": SentinelReport,
    "verification_result": VerificationResult,
    "persona_swap": PersonaSwapOutput,
    "curator": CuratorOutput,
    "atom_batch": AtomBatch,
}


def export_schemas() -> dict[str, dict]:
    return {name: model.model_json_schema() for name, model in SCHEMAS.items()}
