from __future__ import annotations

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    EntityCandidate,
    EntityFactArgument,
    EntityFiller,
    EventCandidate,
    FactCandidateRecord,
    TextFactArgument,
    TextFiller,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import (
    ArgumentBindingCandidateId,
    EntityCandidateId,
    EventCandidateId,
    FactCandidateId,
    ProducerId,
)
from pipeline_v2.types import (
    EntityKind,
    EventRole,
    FactArgumentRole,
    FactKind,
    GroundingKind,
    Signal,
)


def fact_records(document: ArticleDocument) -> tuple[FactCandidateRecord, ...]:
    return tuple(document.materialized_fact_records)


def first_fact_record(document: ArticleDocument) -> FactCandidateRecord:
    return fact_records(document)[0]


def _role_value(role: FactArgumentRole | str) -> str:
    match role:
        case FactArgumentRole():
            return role.value
        case _:
            return role


def entity_argument(
    record: FactCandidateRecord,
    role: FactArgumentRole | str,
) -> EntityCandidateId:
    role_value = _role_value(role)
    for argument in record.arguments:
        match argument:
            case EntityFactArgument(role=argument_role, entity_id=entity_id) if (
                argument_role.value == role_value
            ):
                return entity_id
            case _:
                continue
    raise AssertionError(f"missing entity argument for role {role_value!r}")


def text_argument(record: FactCandidateRecord, role: FactArgumentRole | str) -> str:
    role_value = _role_value(role)
    for argument in record.arguments:
        match argument:
            case TextFactArgument(role=argument_role, value=value) if (
                argument_role.value == role_value
            ):
                return value
            case _:
                continue
    raise AssertionError(f"missing text argument for role {role_value!r}")


def entity_hint_for_role(
    document: ArticleDocument,
    record: FactCandidateRecord,
    role: FactArgumentRole | str,
) -> str | None:
    return document.store.entity_candidates[entity_argument(record, role)].canonical_hint


def entity_kind_for_role(
    document: ArticleDocument,
    record: FactCandidateRecord,
    role: FactArgumentRole | str,
) -> EntityKind:
    return document.store.entity_candidates[entity_argument(record, role)].kind


def argument_roles(record: FactCandidateRecord) -> frozenset[str]:
    roles: set[str] = set()
    for argument in record.arguments:
        match argument:
            case EntityFactArgument(role=role) | TextFactArgument(role=role):
                roles.add(role.value)
    return frozenset(roles)


def fact_record_by_id(
    document: ArticleDocument,
    fact_id: FactCandidateId,
) -> FactCandidateRecord:
    for record in document.materialized_fact_records:
        if record.id == fact_id:
            return record
    raise KeyError(fact_id)


def add_entity(
    document: ArticleDocument,
    *,
    entity_id: EntityCandidateId,
    kind: EntityKind,
    canonical_hint: str | None = None,
    grounding: GroundingKind = GroundingKind.OBSERVED,
    source: ProducerId = ProducerId("test"),
) -> EntityCandidateId:
    return document.store.add_entity_candidate(
        EntityCandidate(
            id=entity_id,
            kind=kind,
            mention_ids=(),
            canonical_hint=canonical_hint,
            grounding=grounding,
            source=source,
        )
    )


def add_event(
    document: ArticleDocument,
    *,
    event_id: EventCandidateId,
    kind: FactKind,
    source: ProducerId = ProducerId("test"),
    signals: tuple[Signal, ...] = (),
) -> EventCandidateId:
    return document.store.add_event_candidate(
        EventCandidate(
            id=event_id,
            kind=kind,
            trigger_evidence_id=None,
            evidence_ids=(),
            source=source,
            signals=signals,
        )
    )


def bind_entity(
    document: ArticleDocument,
    *,
    binding_id: ArgumentBindingCandidateId,
    event_id: EventCandidateId,
    role: EventRole,
    entity_id: EntityCandidateId,
    source: ProducerId = ProducerId("test"),
    signals: tuple[Signal, ...] = (),
) -> None:
    _ = source
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=binding_id,
            event_id=event_id,
            role=role,
            filler=EntityFiller(entity_id),
            evidence_ids=(),
            signals=signals,
        )
    )


def bind_text(
    document: ArticleDocument,
    *,
    binding_id: ArgumentBindingCandidateId,
    event_id: EventCandidateId,
    role: EventRole,
    value: str,
    source: ProducerId = ProducerId("test"),
    signals: tuple[Signal, ...] = (),
) -> None:
    _ = source
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=binding_id,
            event_id=event_id,
            role=role,
            filler=TextFiller(value),
            evidence_ids=(),
            signals=signals,
        )
    )
