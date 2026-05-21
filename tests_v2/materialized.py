from __future__ import annotations

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    EntityCandidate,
    EntityFiller,
    EventCandidate,
    FactCandidateRecord,
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
from pipeline_v2.types import EntityKind, EventRole, FactKind, GroundingKind, Signal


def fact_records(document: ArticleDocument) -> tuple[FactCandidateRecord, ...]:
    return tuple(document.materialized_fact_records)


def first_fact_record(document: ArticleDocument) -> FactCandidateRecord:
    return fact_records(document)[0]


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
    fact_id: FactCandidateId,
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
            source_fact_id=fact_id,
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
