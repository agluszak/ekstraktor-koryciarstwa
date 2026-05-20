from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pipeline_v2.ids import (
    EntityCandidateId,
    EvidenceId,
    FactCandidateId,
    MentionId,
    ProducerId,
    ResolutionClaimId,
    ScorerId,
)
from pipeline_v2.types import (
    EntityKind,
    FactArgumentRole,
    FactKind,
    GroundingKind,
    RelationshipDetail,
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
class PartyAffiliationCandidate:
    id: FactCandidateId
    subject_entity_id: EntityCandidateId
    party_entity_id: EntityCandidateId
    evidence_ids: tuple[EvidenceId, ...]
    source: ProducerId
    signals: tuple[Signal, ...] = ()

    def participating_entity_ids(self) -> tuple[EntityCandidateId, ...]:
        return (self.subject_entity_id, self.party_entity_id)

    def to_fact_record(self) -> "FactCandidateRecord":
        return FactCandidateRecord(
            id=self.id,
            kind=FactKind.PARTY_AFFILIATION,
            arguments=(
                EntityFactArgument(FactArgumentRole.SUBJECT, self.subject_entity_id),
                EntityFactArgument(FactArgumentRole.OBJECT, self.party_entity_id),
            ),
            evidence_ids=self.evidence_ids,
            source=self.source,
            signals=self.signals,
        )


@dataclass(frozen=True, slots=True)
class PoliticalSupportCandidate:
    id: FactCandidateId
    supporter_entity_id: EntityCandidateId
    supported_entity_id: EntityCandidateId
    evidence_ids: tuple[EvidenceId, ...]
    source: ProducerId
    signals: tuple[Signal, ...] = ()

    def participating_entity_ids(self) -> tuple[EntityCandidateId, ...]:
        return (self.supporter_entity_id, self.supported_entity_id)

    def to_fact_record(self) -> "FactCandidateRecord":
        arguments: list[FactArgument] = [
            EntityFactArgument(FactArgumentRole.SUBJECT, self.supporter_entity_id),
            EntityFactArgument(FactArgumentRole.OBJECT, self.supported_entity_id),
        ]
        return FactCandidateRecord(
            id=self.id,
            kind=FactKind.POLITICAL_SUPPORT,
            arguments=tuple(arguments),
            evidence_ids=self.evidence_ids,
            source=self.source,
            signals=self.signals,
        )


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
class GovernanceFactCandidate:
    id: FactCandidateId
    kind: FactKind
    person_entity_id: EntityCandidateId
    organization_entity_id: EntityCandidateId | None
    role_entity_id: EntityCandidateId | None
    evidence_ids: tuple[EvidenceId, ...]
    source: ProducerId
    signals: tuple[Signal, ...] = ()

    def participating_entity_ids(self) -> tuple[EntityCandidateId, ...]:
        ids = [self.person_entity_id]
        if self.organization_entity_id is not None:
            ids.append(self.organization_entity_id)
        if self.role_entity_id is not None:
            ids.append(self.role_entity_id)
        return tuple(ids)

    def to_fact_record(self) -> FactCandidateRecord:
        arguments: list[FactArgument] = [
            EntityFactArgument(FactArgumentRole.PERSON, self.person_entity_id)
        ]
        if self.organization_entity_id is not None:
            arguments.append(
                EntityFactArgument(FactArgumentRole.ORGANIZATION, self.organization_entity_id)
            )
        if self.role_entity_id is not None:
            arguments.append(EntityFactArgument(FactArgumentRole.ROLE, self.role_entity_id))
        return FactCandidateRecord(
            id=self.id,
            kind=self.kind,
            arguments=tuple(arguments),
            evidence_ids=self.evidence_ids,
            source=self.source,
            signals=self.signals,
        )


@dataclass(frozen=True, slots=True)
class PublicEmploymentFactCandidate:
    id: FactCandidateId
    person_entity_id: EntityCandidateId
    organization_entity_id: EntityCandidateId
    role_entity_id: EntityCandidateId | None
    evidence_ids: tuple[EvidenceId, ...]
    source: ProducerId
    signals: tuple[Signal, ...] = ()
    context_text: str | None = None

    def participating_entity_ids(self) -> tuple[EntityCandidateId, ...]:
        ids = [self.person_entity_id, self.organization_entity_id]
        if self.role_entity_id is not None:
            ids.append(self.role_entity_id)
        return tuple(ids)

    def to_fact_record(self) -> FactCandidateRecord:
        arguments: list[FactArgument] = [
            EntityFactArgument(FactArgumentRole.PERSON, self.person_entity_id),
            EntityFactArgument(FactArgumentRole.ORGANIZATION, self.organization_entity_id),
        ]
        if self.role_entity_id is not None:
            arguments.append(EntityFactArgument(FactArgumentRole.ROLE, self.role_entity_id))
        if self.context_text is not None:
            arguments.append(TextFactArgument(FactArgumentRole.CONTEXT, self.context_text))
        return FactCandidateRecord(
            id=self.id,
            kind=FactKind.PUBLIC_EMPLOYMENT,
            arguments=tuple(arguments),
            evidence_ids=self.evidence_ids,
            source=self.source,
            signals=self.signals,
        )


@dataclass(frozen=True, slots=True)
class PersonalTieFactCandidate:
    id: FactCandidateId
    subject_entity_id: EntityCandidateId
    object_entity_id: EntityCandidateId
    evidence_ids: tuple[EvidenceId, ...]
    source: ProducerId
    signals: tuple[Signal, ...] = ()
    relationship_detail: RelationshipDetail | None = None
    context_text: str | None = None

    def participating_entity_ids(self) -> tuple[EntityCandidateId, ...]:
        return (self.subject_entity_id, self.object_entity_id)

    def to_fact_record(self) -> FactCandidateRecord:
        arguments: list[FactArgument] = [
            EntityFactArgument(FactArgumentRole.SUBJECT, self.subject_entity_id),
            EntityFactArgument(FactArgumentRole.OBJECT, self.object_entity_id),
        ]
        if self.relationship_detail is not None:
            arguments.append(
                TextFactArgument(
                    FactArgumentRole.RELATIONSHIP_DETAIL,
                    self.relationship_detail.value,
                )
            )
        if self.context_text is not None:
            arguments.append(TextFactArgument(FactArgumentRole.CONTEXT, self.context_text))
        return FactCandidateRecord(
            id=self.id,
            kind=FactKind.PERSONAL_OR_POLITICAL_TIE,
            arguments=tuple(arguments),
            evidence_ids=self.evidence_ids,
            source=self.source,
            signals=self.signals,
        )


@dataclass(frozen=True, slots=True)
class MoneyTransferFactCandidate:
    id: FactCandidateId
    kind: FactKind
    source_entity_id: EntityCandidateId | None
    target_entity_id: EntityCandidateId | None
    amount_text: str | None
    evidence_ids: tuple[EvidenceId, ...]
    source: ProducerId
    signals: tuple[Signal, ...] = ()

    def participating_entity_ids(self) -> tuple[EntityCandidateId, ...]:
        ids: list[EntityCandidateId] = []
        if self.source_entity_id is not None:
            ids.append(self.source_entity_id)
        if self.target_entity_id is not None:
            ids.append(self.target_entity_id)
        return tuple(ids)

    def to_fact_record(self) -> FactCandidateRecord:
        arguments: list[FactArgument] = []
        if self.source_entity_id is not None:
            arguments.append(
                EntityFactArgument(self._source_argument_role(), self.source_entity_id)
            )
        if self.target_entity_id is not None:
            arguments.append(
                EntityFactArgument(self._target_argument_role(), self.target_entity_id)
            )
        if self.amount_text is not None:
            arguments.append(TextFactArgument(FactArgumentRole.AMOUNT, self.amount_text))
        return FactCandidateRecord(
            id=self.id,
            kind=self.kind,
            arguments=tuple(arguments),
            evidence_ids=self.evidence_ids,
            source=self.source,
            signals=self.signals,
        )

    def _source_argument_role(self) -> FactArgumentRole:
        if self.kind == FactKind.PUBLIC_CONTRACT:
            return FactArgumentRole.COUNTERPARTY
        return FactArgumentRole.FUNDER

    def _target_argument_role(self) -> FactArgumentRole:
        if self.kind == FactKind.PUBLIC_CONTRACT:
            return FactArgumentRole.CONTRACTOR
        return FactArgumentRole.RECIPIENT


@dataclass(frozen=True, slots=True)
class AntiCorruptionReferralCandidate:
    id: FactCandidateId
    actor_entity_id: EntityCandidateId | None
    target_entity_id: EntityCandidateId | None
    institution_entity_id: EntityCandidateId | None
    evidence_ids: tuple[EvidenceId, ...]
    source: ProducerId
    signals: tuple[Signal, ...] = ()
    institution_text: str | None = None
    context_text: str | None = None

    def participating_entity_ids(self) -> tuple[EntityCandidateId, ...]:
        ids: list[EntityCandidateId] = []
        if self.actor_entity_id is not None:
            ids.append(self.actor_entity_id)
        if self.target_entity_id is not None:
            ids.append(self.target_entity_id)
        if self.institution_entity_id is not None:
            ids.append(self.institution_entity_id)
        return tuple(ids)

    def to_fact_record(self) -> FactCandidateRecord:
        arguments: list[FactArgument] = []
        if self.actor_entity_id is not None:
            arguments.append(EntityFactArgument(FactArgumentRole.COMPLAINANT, self.actor_entity_id))
        if self.target_entity_id is not None:
            arguments.append(EntityFactArgument(FactArgumentRole.TARGET, self.target_entity_id))
        if self.institution_entity_id is not None:
            arguments.append(
                EntityFactArgument(FactArgumentRole.INSTITUTION, self.institution_entity_id)
            )
        elif self.institution_text is not None:
            arguments.append(TextFactArgument(FactArgumentRole.INSTITUTION, self.institution_text))
        if self.context_text is not None:
            arguments.append(TextFactArgument(FactArgumentRole.CONTEXT, self.context_text))
        return FactCandidateRecord(
            id=self.id,
            kind=FactKind.ANTI_CORRUPTION_REFERRAL,
            arguments=tuple(arguments),
            evidence_ids=self.evidence_ids,
            source=self.source,
            signals=self.signals,
        )


@dataclass(frozen=True, slots=True)
class AntiCorruptionInvestigationCandidate:
    id: FactCandidateId
    target_entity_id: EntityCandidateId | None
    institution_entity_id: EntityCandidateId | None
    evidence_ids: tuple[EvidenceId, ...]
    source: ProducerId
    signals: tuple[Signal, ...] = ()
    institution_text: str | None = None
    context_text: str | None = None

    def participating_entity_ids(self) -> tuple[EntityCandidateId, ...]:
        ids: list[EntityCandidateId] = []
        if self.target_entity_id is not None:
            ids.append(self.target_entity_id)
        if self.institution_entity_id is not None:
            ids.append(self.institution_entity_id)
        return tuple(ids)

    def to_fact_record(self) -> FactCandidateRecord:
        arguments: list[FactArgument] = []
        if self.target_entity_id is not None:
            arguments.append(EntityFactArgument(FactArgumentRole.TARGET, self.target_entity_id))
        if self.institution_entity_id is not None:
            arguments.append(
                EntityFactArgument(FactArgumentRole.INSTITUTION, self.institution_entity_id)
            )
        elif self.institution_text is not None:
            arguments.append(TextFactArgument(FactArgumentRole.INSTITUTION, self.institution_text))
        if self.context_text is not None:
            arguments.append(TextFactArgument(FactArgumentRole.CONTEXT, self.context_text))
        return FactCandidateRecord(
            id=self.id,
            kind=FactKind.ANTI_CORRUPTION_INVESTIGATION,
            arguments=tuple(arguments),
            evidence_ids=self.evidence_ids,
            source=self.source,
            signals=self.signals,
        )


@dataclass(frozen=True, slots=True)
class BinaryFactCandidate:
    id: FactCandidateId
    kind: FactKind
    subject_entity_id: EntityCandidateId
    object_entity_id: EntityCandidateId | None
    evidence_ids: tuple[EvidenceId, ...]
    source: ProducerId
    signals: tuple[Signal, ...] = ()
    value_text: str | None = None

    def participating_entity_ids(self) -> tuple[EntityCandidateId, ...]:
        if self.object_entity_id is None:
            return (self.subject_entity_id,)
        return (self.subject_entity_id, self.object_entity_id)

    def to_fact_record(self) -> FactCandidateRecord:
        arguments: list[FactArgument] = [
            EntityFactArgument(FactArgumentRole.SUBJECT, self.subject_entity_id)
        ]
        if self.object_entity_id is not None:
            arguments.append(EntityFactArgument(FactArgumentRole.OBJECT, self.object_entity_id))
        if self.value_text is not None:
            arguments.append(TextFactArgument(FactArgumentRole.CONTEXT, self.value_text))
        return FactCandidateRecord(
            id=self.id,
            kind=self.kind,
            arguments=tuple(arguments),
            evidence_ids=self.evidence_ids,
            source=self.source,
            signals=self.signals,
        )


class FactCandidate(Protocol):
    id: FactCandidateId

    def participating_entity_ids(self) -> tuple[EntityCandidateId, ...]: ...

    def to_fact_record(self) -> FactCandidateRecord: ...


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
