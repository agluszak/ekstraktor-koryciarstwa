from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pipeline_v2.types import (
    AppointerContextSignal,
    CompensationRecipientSignal,
    CompensationSourceSignal,
    ContractCounterpartySignal,
    ContractorSignal,
    ControllerContextSignal,
    DirectPrepositionalAttachmentSignal,
    EventRole,
    FactKind,
    FunderSignal,
    ImplausiblePersonBindingSignal,
    LocalActorSignal,
    LocalObjectSignal,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    LocalSubjectSignal,
    LocalTargetSignal,
    PartyOrganizationSignal,
    PossessiveKinshipSignal,
    ProxyFamilyEntitySignal,
    RecipientSignal,
    SelfTieContradictionSignal,
    Signal,
    SignalPolarity,
    WeakSyntacticBindingSignal,
    WindowFallbackSignal,
    WindowOrganizationSignal,
    WindowPersonSignal,
    WindowRoleSignal,
)


class RoleSignalWeightPolicy(Protocol):
    def applies_to(self, fact_kind: FactKind | None) -> bool: ...

    def contribution(self, signal: Signal, *, role: EventRole | None) -> float | None: ...


class RoleBaseWeightPolicy:
    def contribution(self, role: EventRole | None, is_unknown: bool) -> float:
        if is_unknown:
            return 0.7
        if role in {EventRole.EMPLOYEE, EventRole.PERSON, EventRole.SUBJECT, EventRole.OBJECT}:
            return 0.1
        if role in {
            EventRole.WORKPLACE,
            EventRole.ORGANIZATION,
            EventRole.FUNDER,
            EventRole.RECIPIENT,
        }:
            return 0.08
        return 0.0


@dataclass(frozen=True, slots=True)
class LocalityRoleSignalPolicy:
    def applies_to(self, fact_kind: FactKind | None) -> bool:
        _ = fact_kind
        return True

    def contribution(self, signal: Signal, *, role: EventRole | None) -> float | None:
        _ = role
        match signal:
            case LocalPersonSignal() | LocalOrganizationSignal() | LocalRoleSignal():
                return 0.35
            case LocalActorSignal() | LocalTargetSignal():
                return 0.32
            case LocalSubjectSignal() | LocalObjectSignal():
                return 0.28
            case WindowPersonSignal() | WindowOrganizationSignal() | WindowRoleSignal():
                return 0.15
            case WindowFallbackSignal():
                return 0.12
            case _:
                return None


@dataclass(frozen=True, slots=True)
class FamilyProxyRoleSignalPolicy:
    def applies_to(self, fact_kind: FactKind | None) -> bool:
        return fact_kind in {
            FactKind.PUBLIC_EMPLOYMENT,
            FactKind.KINSHIP_TIE,
            FactKind.PERSONAL_OR_POLITICAL_TIE,
        }

    def contribution(self, signal: Signal, *, role: EventRole | None) -> float | None:
        _ = role
        match signal:
            case ProxyFamilyEntitySignal() | PossessiveKinshipSignal():
                return 0.35
            case _:
                return None


@dataclass(frozen=True, slots=True)
class NegativeContextRoleSignalPolicy:
    def applies_to(self, fact_kind: FactKind | None) -> bool:
        _ = fact_kind
        return True

    def contribution(self, signal: Signal, *, role: EventRole | None) -> float | None:
        _ = role
        match signal:
            case (
                WeakSyntacticBindingSignal()
                | AppointerContextSignal()
                | ControllerContextSignal()
                | ImplausiblePersonBindingSignal()
                | PartyOrganizationSignal()
                | SelfTieContradictionSignal()
            ):
                return -0.85
            case _:
                return None


@dataclass(frozen=True, slots=True)
class PublicMoneyRoleSignalPolicy:
    def applies_to(self, fact_kind: FactKind | None) -> bool:
        return fact_kind in {
            FactKind.FUNDING,
            FactKind.PUBLIC_CONTRACT,
            FactKind.COMPENSATION,
        }

    def contribution(self, signal: Signal, *, role: EventRole | None) -> float | None:
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


@dataclass(frozen=True, slots=True)
class PolarityFallbackRoleSignalPolicy:
    def applies_to(self, fact_kind: FactKind | None) -> bool:
        _ = fact_kind
        return True

    def contribution(self, signal: Signal, *, role: EventRole | None) -> float | None:
        _ = role
        if signal.polarity is SignalPolarity.POSITIVE:
            return 0.18
        return -0.22


class RoleSignalWeightRegistry:
    def __init__(self, policies: tuple[RoleSignalWeightPolicy, ...] | None = None) -> None:
        self.policies = policies or (
            LocalityRoleSignalPolicy(),
            FamilyProxyRoleSignalPolicy(),
            NegativeContextRoleSignalPolicy(),
            PublicMoneyRoleSignalPolicy(),
            PolarityFallbackRoleSignalPolicy(),
        )

    def contribution(
        self,
        signal: Signal,
        *,
        fact_kind: FactKind | None,
        role: EventRole | None,
    ) -> float:
        for policy in self.policies:
            if not policy.applies_to(fact_kind):
                continue
            contribution = policy.contribution(signal, role=role)
            if contribution is not None:
                return contribution
        return 0.0
