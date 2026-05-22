from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.ids import (
    ArgumentBindingCandidateId,
    EntityCandidateId,
    EventCandidateId,
    EvidenceId,
    FactCandidateId,
    MentionId,
    ProducerId,
    ResolutionClaimId,
    ScorerId,
)
from pipeline_v2.types import (
    EntityKind,
    EventRole,
    FactArgumentRole,
    FactKind,
    GroundingKind,
    ResolutionRelation,
    Signal,
)


@dataclass(frozen=True, slots=True)
class FullPersonNameKey:
    given_name_lemma: str
    surname_base: str


@dataclass(frozen=True, slots=True)
class OrganizationAcronymKey:
    acronym: str


type EntityBlockingKey = FullPersonNameKey | OrganizationAcronymKey
type EntityReuseKey = FullPersonNameKey


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    id: EntityCandidateId
    kind: EntityKind
    mention_ids: tuple[MentionId, ...]
    canonical_hint: str | None
    grounding: GroundingKind
    source: ProducerId
    reference_ids: tuple[MentionId, ...] = ()
    blocking_key: EntityBlockingKey | None = None
    reuse_key: EntityReuseKey | None = None

    def person_surname_base(self) -> str | None:
        if self.reuse_key is None:
            return None
        return self.reuse_key.surname_base


@dataclass(frozen=True, slots=True)
class EntityFactArgument:
    role: FactArgumentRole
    entity_id: EntityCandidateId

    def to_json(self) -> dict[str, str]:
        return {"role": self.role.value, "entity_id": str(self.entity_id)}


@dataclass(frozen=True, slots=True)
class TextFactArgument:
    role: FactArgumentRole
    value: str

    def to_json(self) -> dict[str, str]:
        return {"role": self.role.value, "value": self.value}


type FactArgument = EntityFactArgument | TextFactArgument


@dataclass(frozen=True, slots=True)
class EntityFiller:
    entity_id: EntityCandidateId


@dataclass(frozen=True, slots=True)
class TextFiller:
    value: str


@dataclass(frozen=True, slots=True)
class UnknownFiller:
    reason: str = "unknown"


type ArgumentFiller = EntityFiller | TextFiller | UnknownFiller


@dataclass(frozen=True, slots=True)
class EventCandidate:
    id: EventCandidateId
    kind: FactKind
    trigger_evidence_id: EvidenceId | None
    evidence_ids: tuple[EvidenceId, ...]
    source: ProducerId
    signals: tuple[Signal, ...] = ()


@dataclass(frozen=True, slots=True)
class ArgumentBindingCandidate:
    id: ArgumentBindingCandidateId
    event_id: EventCandidateId
    role: EventRole
    filler: ArgumentFiller
    evidence_ids: tuple[EvidenceId, ...]
    signals: tuple[Signal, ...] = ()


@dataclass(frozen=True, slots=True)
class FactCandidateRecord:
    id: FactCandidateId
    kind: FactKind
    arguments: tuple[FactArgument, ...]
    evidence_ids: tuple[EvidenceId, ...]
    source: ProducerId
    signals: tuple[Signal, ...] = ()

    def to_json(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "kind": self.kind.value,
            "arguments": [argument.to_json() for argument in self.arguments],
            "evidence_ids": [str(evidence_id) for evidence_id in self.evidence_ids],
            "source": str(self.source),
            "signals": [signal.to_json() for signal in self.signals],
        }


@dataclass(frozen=True, slots=True)
class MaterializedRoleAlternative:
    role: FactArgumentRole
    filler: FactArgument
    posterior: float
    evidence_ids: tuple[EvidenceId, ...]
    signals: tuple[Signal, ...] = ()

    def to_json(self) -> dict[str, object]:
        return {
            "role": self.role.value,
            "filler": self.filler.to_json(),
            "posterior": self.posterior,
            "evidence_ids": [str(evidence_id) for evidence_id in self.evidence_ids],
            "signals": [signal.to_json() for signal in self.signals],
        }


@dataclass(frozen=True, slots=True)
class Assessment:
    score: float
    positive_signals: tuple[Signal, ...]
    negative_signals: tuple[Signal, ...]
    scorer_id: ScorerId
    explanation: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"assessment score must be in [0.0, 1.0], got {self.score}")


@dataclass(frozen=True, slots=True)
class EntityResolutionProposal:
    left_entity_id: EntityCandidateId
    right_entity_id: EntityCandidateId
    evidence_ids: tuple[EvidenceId, ...]
    retrieval_signals: tuple[Signal, ...] = ()
    context_signals: tuple[Signal, ...] = ()


@dataclass(frozen=True, slots=True)
class ReferenceResolutionProposal:
    reference_id: MentionId
    candidate_entity_id: EntityCandidateId
    evidence_ids: tuple[EvidenceId, ...]
    retrieval_signals: tuple[Signal, ...] = ()
    context_signals: tuple[Signal, ...] = ()


@dataclass(frozen=True, slots=True)
class EntityResolutionClaim:
    id: ResolutionClaimId
    left_entity_id: EntityCandidateId
    right_entity_id: EntityCandidateId
    relation: ResolutionRelation
    evidence_ids: tuple[EvidenceId, ...]
    assessment: Assessment
    source: ProducerId


@dataclass(frozen=True, slots=True)
class ReferenceResolutionClaim:
    id: ResolutionClaimId
    reference_id: MentionId
    candidate_entity_id: EntityCandidateId
    relation: ResolutionRelation
    evidence_ids: tuple[EvidenceId, ...]
    assessment: Assessment
    source: ProducerId


@dataclass(frozen=True, slots=True)
class FactResolutionProposal:
    left_fact_id: FactCandidateId
    right_fact_id: FactCandidateId
    relation: ResolutionRelation
    evidence_ids: tuple[EvidenceId, ...]
    retrieval_signals: tuple[Signal, ...] = ()
    context_signals: tuple[Signal, ...] = ()


@dataclass(frozen=True, slots=True)
class FactResolutionClaim:
    id: ResolutionClaimId
    left_fact_id: FactCandidateId
    right_fact_id: FactCandidateId
    relation: ResolutionRelation
    evidence_ids: tuple[EvidenceId, ...]
    assessment: Assessment
    source: ProducerId


@dataclass(frozen=True, slots=True)
class MaterializedFactAlternative:
    record: FactCandidateRecord
    score: float
    claim_id: ResolutionClaimId
    relation: ResolutionRelation

    def to_json(self) -> dict[str, object]:
        return {
            "record": self.record.to_json(),
            "score": self.score,
            "claim_id": str(self.claim_id),
            "relation": self.relation.value,
        }
