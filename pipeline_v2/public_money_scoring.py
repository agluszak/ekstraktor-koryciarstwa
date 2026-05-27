from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.types import (
    CompensationRecipientSignal,
    CompensationSourceSignal,
    ContractCounterpartySignal,
    ContractorSignal,
    DirectPrepositionalAttachmentSignal,
    EventRole,
    FactKind,
    FunderSignal,
    RecipientSignal,
    Signal,
)


@dataclass(frozen=True, slots=True)
class PublicMoneyRoleSignalPolicy:
    """Role-filler weights for public-money bindings.

    The generic inference builder composes this policy through the role-scoring
    registry, but the domain-specific signal meanings live beside the producer.
    """

    def applies_to(self, fact_kind: FactKind | None) -> bool:
        return fact_kind in {
            FactKind.FUNDING,
            FactKind.PUBLIC_CONTRACT,
            FactKind.COMPENSATION,
        }

    def contribution(self, signal: Signal, *, role: EventRole | None) -> float | None:
        _ = role
        match signal:
            case (
                ContractCounterpartySignal()
                | ContractorSignal()
                | FunderSignal()
                | RecipientSignal()
                | CompensationSourceSignal()
                | CompensationRecipientSignal()
            ):
                return 0.34
            case DirectPrepositionalAttachmentSignal():
                return 0.42
            case _:
                return None
