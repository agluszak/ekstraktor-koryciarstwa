from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pipeline_v2.ids import EvidenceId, InferenceFactorId, InferenceStateId, InferenceVariableId
from pipeline_v2.types import EventRole, FactKind, Signal


class InferenceVariableKind(StrEnum):
    EVENT_ACTIVE = "event_active"
    ROLE_FILLER = "role_filler"
    ENTITY_ATTRIBUTE = "entity_attribute"
    SAME_ENTITY = "same_entity"
    REFERENCE_TARGET = "reference_target"
    SAME_EVENT = "same_event"


class InferenceFactorKind(StrEnum):
    EVIDENCE_PRIOR = "evidence_prior"
    ROLE_PRIOR = "role_prior"
    ROLE_COMPATIBILITY = "role_compatibility"
    COMPETITION = "competition"
    CONSTRAINT = "constraint"


@dataclass(frozen=True, slots=True)
class InferenceState:
    id: InferenceStateId
    label: str


@dataclass(frozen=True, slots=True)
class InferenceVariable:
    id: InferenceVariableId
    kind: InferenceVariableKind
    states: tuple[InferenceState, ...]
    fact_kind: FactKind | None = None
    role: EventRole | None = None


@dataclass(frozen=True, slots=True)
class InferenceFactor:
    id: InferenceFactorId
    kind: InferenceFactorKind
    variable_ids: tuple[InferenceVariableId, ...]
    potentials: tuple[float, ...]
    evidence_ids: tuple[EvidenceId, ...] = ()
    signals: tuple[Signal, ...] = ()


@dataclass(frozen=True, slots=True)
class InferenceGraphSpec:
    variables: tuple[InferenceVariable, ...]
    factors: tuple[InferenceFactor, ...]


@dataclass(frozen=True, slots=True)
class StateProbability:
    state_id: InferenceStateId
    probability: float


@dataclass(frozen=True, slots=True)
class VariableMarginal:
    variable_id: InferenceVariableId
    probabilities: tuple[StateProbability, ...]

    def probability_for(self, state_id: InferenceStateId) -> float:
        for probability in self.probabilities:
            if probability.state_id == state_id:
                return probability.probability
        return 0.0


@dataclass(frozen=True, slots=True)
class InferenceDiagnostic:
    message: str


@dataclass(frozen=True, slots=True)
class InferenceResult:
    marginals: tuple[VariableMarginal, ...]
    diagnostics: tuple[InferenceDiagnostic, ...] = ()

    def marginal_for(self, variable_id: InferenceVariableId) -> VariableMarginal | None:
        for marginal in self.marginals:
            if marginal.variable_id == variable_id:
                return marginal
        return None
