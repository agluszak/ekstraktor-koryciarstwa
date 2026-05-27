from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.domain_emitter import DomainEventEmitter, EmittedEvent
from pipeline_v2.ids import EntityCandidateId, EvidenceId
from pipeline_v2.types import EventRole, Signal


@dataclass(frozen=True, slots=True)
class EntityBindingGroup:
    role: EventRole
    bindings: tuple[tuple[EntityCandidateId, tuple[Signal, ...]], ...]


def merge_binding_signals(
    existing: tuple[Signal, ...],
    new: tuple[Signal, ...],
) -> tuple[Signal, ...]:
    return tuple(dict.fromkeys([*existing, *new]))


def emit_entity_binding_groups(
    *,
    emitter: DomainEventEmitter,
    event: EmittedEvent,
    evidence_id: EvidenceId,
    groups: tuple[EntityBindingGroup, ...],
) -> None:
    for group in groups:
        for entity_id, signals in group.bindings:
            if not signals:
                continue
            emitter.bind_entity(
                event=event,
                role=group.role,
                entity_id=entity_id,
                evidence_ids=(evidence_id,),
                signals=signals,
            )
