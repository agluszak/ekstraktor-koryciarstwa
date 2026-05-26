from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    ArgumentFiller,
    EntityFiller,
    EventCandidate,
    TextFiller,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, EventCandidateId, EvidenceId, ProducerId
from pipeline_v2.types import EventRole, FactKind, Signal


@dataclass(frozen=True, slots=True)
class EmittedEvent:
    id: EventCandidateId


@dataclass(frozen=True, slots=True)
class DomainEventEmitter:
    """Single write path for domain event and role-binding hypotheses.

    Domain producers should decide what hypotheses are admissible for graph
    shape, then use this facade to emit all competing fillers. Scoring and
    winner selection belong in inference factors.
    """

    document: ArticleDocument
    producer_id: ProducerId

    def event(
        self,
        *,
        kind: FactKind,
        trigger_evidence_id: EvidenceId | None,
        evidence_ids: tuple[EvidenceId, ...],
        signals: tuple[Signal, ...] = (),
    ) -> EmittedEvent:
        event = EventCandidate(
            id=self.document.store.next_event_candidate_id(),
            kind=kind,
            trigger_evidence_id=trigger_evidence_id,
            evidence_ids=evidence_ids,
            source=self.producer_id,
            signals=signals,
        )
        self.document.store.add_event_candidate(event)
        return EmittedEvent(id=event.id)

    def bind_entity(
        self,
        *,
        event: EmittedEvent,
        role: EventRole,
        entity_id: EntityCandidateId,
        evidence_ids: tuple[EvidenceId, ...],
        signals: tuple[Signal, ...] = (),
    ) -> None:
        self.bind(
            event=event,
            role=role,
            filler=EntityFiller(entity_id),
            evidence_ids=evidence_ids,
            signals=signals,
        )

    def bind_text(
        self,
        *,
        event: EmittedEvent,
        role: EventRole,
        value: str,
        evidence_ids: tuple[EvidenceId, ...],
        signals: tuple[Signal, ...] = (),
    ) -> None:
        self.bind(
            event=event,
            role=role,
            filler=TextFiller(value),
            evidence_ids=evidence_ids,
            signals=signals,
        )

    def bind(
        self,
        *,
        event: EmittedEvent,
        role: EventRole,
        filler: ArgumentFiller,
        evidence_ids: tuple[EvidenceId, ...],
        signals: tuple[Signal, ...] = (),
    ) -> None:
        self.document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=self.document.store.next_argument_binding_candidate_id(),
                event_id=event.id,
                role=role,
                filler=filler,
                evidence_ids=evidence_ids,
                signals=signals,
            )
        )
