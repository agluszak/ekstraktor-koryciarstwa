from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pipeline_v2.candidates import EntityFiller
from pipeline_v2.document import ArticleDocument
from pipeline_v2.types import (
    DomainOverlapSuppressionSignal,
    EventRole,
    FactKind,
    ImplausiblePersonBindingSignal,
    Signal,
    SignalPolarity,
    WeakSyntacticBindingSignal,
)

if TYPE_CHECKING:
    from .factor_builders import RoleFillerState


class RolePairFactorPolicy(Protocol):
    def applies_to(
        self,
        *,
        fact_kind: FactKind,
        left_role: EventRole,
        right_role: EventRole,
    ) -> bool: ...

    def multiplier(
        self,
        *,
        document: ArticleDocument,
        left_state: RoleFillerState,
        right_state: RoleFillerState,
    ) -> float | None: ...


@dataclass(frozen=True, slots=True)
class SharedEvidenceRolePairPolicy:
    """Boost role choices grounded in the same evidence.

    This is intentionally generic. More domain-specific pair policies can be
    added without growing the graph builder.
    """

    supported_pairs: frozenset[tuple[FactKind, EventRole, EventRole]]

    def applies_to(
        self,
        *,
        fact_kind: FactKind,
        left_role: EventRole,
        right_role: EventRole,
    ) -> bool:
        return _normalized_pair(fact_kind, left_role, right_role) in self.supported_pairs

    def multiplier(
        self,
        *,
        document: ArticleDocument,
        left_state: RoleFillerState,
        right_state: RoleFillerState,
    ) -> float | None:
        _ = document
        if left_state.filler is None or right_state.filler is None:
            return None
        if _has_negative_binding(left_state.signals) or _has_negative_binding(right_state.signals):
            return None
        if set(left_state.evidence_ids) & set(right_state.evidence_ids):
            return 1.18
        return None


@dataclass(frozen=True, slots=True)
class WeakBindingRolePairPolicy:
    supported_pairs: frozenset[tuple[FactKind, EventRole, EventRole]]

    def applies_to(
        self,
        *,
        fact_kind: FactKind,
        left_role: EventRole,
        right_role: EventRole,
    ) -> bool:
        return _normalized_pair(fact_kind, left_role, right_role) in self.supported_pairs

    def multiplier(
        self,
        *,
        document: ArticleDocument,
        left_state: RoleFillerState,
        right_state: RoleFillerState,
    ) -> float | None:
        _ = document
        if left_state.filler is None or right_state.filler is None:
            return None
        if _has_weak_binding(left_state.signals) or _has_weak_binding(right_state.signals):
            return 0.45
        return None


@dataclass(frozen=True, slots=True)
class ResolvedSameEntityRolePairPolicy:
    supported_pairs: frozenset[tuple[FactKind, EventRole, EventRole]]

    def applies_to(
        self,
        *,
        fact_kind: FactKind,
        left_role: EventRole,
        right_role: EventRole,
    ) -> bool:
        return _normalized_pair(fact_kind, left_role, right_role) in self.supported_pairs

    def multiplier(
        self,
        *,
        document: ArticleDocument,
        left_state: RoleFillerState,
        right_state: RoleFillerState,
    ) -> float | None:
        match (left_state.filler, right_state.filler):
            case (EntityFiller(entity_id=left_id), EntityFiller(entity_id=right_id)):
                if left_id == right_id:
                    return 0.03
                left = document.store.entity_candidates.get(left_id)
                right = document.store.entity_candidates.get(right_id)
                if (
                    left is not None
                    and right is not None
                    and left.canonical_hint
                    and left.canonical_hint.casefold() == (right.canonical_hint or "").casefold()
                ):
                    return 0.2
            case _:
                return None
        return None


class RolePairFactorRegistry:
    def __init__(self, policies: tuple[RolePairFactorPolicy, ...] | None = None) -> None:
        pairs = _default_supported_pairs()
        self.policies = policies or (
            ResolvedSameEntityRolePairPolicy(pairs),
            WeakBindingRolePairPolicy(pairs),
            SharedEvidenceRolePairPolicy(pairs),
        )

    def applies_to(
        self,
        *,
        fact_kind: FactKind,
        left_role: EventRole,
        right_role: EventRole,
    ) -> bool:
        return any(
            policy.applies_to(
                fact_kind=fact_kind,
                left_role=left_role,
                right_role=right_role,
            )
            for policy in self.policies
        )

    def multiplier(
        self,
        *,
        fact_kind: FactKind,
        left_role: EventRole,
        right_role: EventRole,
        document: ArticleDocument,
        left_state: RoleFillerState,
        right_state: RoleFillerState,
    ) -> float:
        score = 1.0
        for policy in self.policies:
            if not policy.applies_to(
                fact_kind=fact_kind,
                left_role=left_role,
                right_role=right_role,
            ):
                continue
            contribution = policy.multiplier(
                document=document,
                left_state=left_state,
                right_state=right_state,
            )
            if contribution is not None:
                score *= contribution
        return score


def _has_weak_binding(signals: tuple[Signal, ...]) -> bool:
    for signal in signals:
        match signal:
            case WeakSyntacticBindingSignal():
                return True
            case _:
                continue
    return False


def _has_negative_binding(signals: tuple[Signal, ...]) -> bool:
    for signal in signals:
        match signal:
            case (
                DomainOverlapSuppressionSignal()
                | ImplausiblePersonBindingSignal()
                | WeakSyntacticBindingSignal()
            ):
                return True
            case _ if signal.polarity is SignalPolarity.NEGATIVE:
                return True
            case _:
                continue
    return False


def _default_supported_pairs() -> frozenset[tuple[FactKind, EventRole, EventRole]]:
    return frozenset(
        _normalized_pair(fact_kind, left_role, right_role)
        for fact_kind, left_role, right_role in (
            (FactKind.PUBLIC_ROLE_APPOINTMENT, EventRole.PERSON, EventRole.ROLE),
            (FactKind.PUBLIC_ROLE_APPOINTMENT, EventRole.PERSON, EventRole.ORGANIZATION),
            (FactKind.PUBLIC_ROLE_APPOINTMENT, EventRole.ROLE, EventRole.ORGANIZATION),
            (FactKind.PUBLIC_ROLE_HOLDING, EventRole.PERSON, EventRole.ROLE),
            (FactKind.PUBLIC_ROLE_HOLDING, EventRole.PERSON, EventRole.ORGANIZATION),
            (FactKind.PUBLIC_ROLE_HOLDING, EventRole.ROLE, EventRole.ORGANIZATION),
            (FactKind.PUBLIC_ROLE_END, EventRole.PERSON, EventRole.ROLE),
            (FactKind.PUBLIC_ROLE_END, EventRole.PERSON, EventRole.ORGANIZATION),
            (FactKind.PUBLIC_ROLE_END, EventRole.ROLE, EventRole.ORGANIZATION),
            (FactKind.PUBLIC_EMPLOYMENT, EventRole.EMPLOYEE, EventRole.WORKPLACE),
            (FactKind.PUBLIC_EMPLOYMENT, EventRole.EMPLOYEE, EventRole.ROLE),
            (FactKind.PUBLIC_EMPLOYMENT, EventRole.EMPLOYEE, EventRole.HIRING_AUTHORITY),
            (FactKind.PUBLIC_EMPLOYMENT, EventRole.WORKPLACE, EventRole.ROLE),
            (FactKind.FUNDING, EventRole.FUNDER, EventRole.RECIPIENT),
            (FactKind.PUBLIC_CONTRACT, EventRole.COUNTERPARTY, EventRole.CONTRACTOR),
            (FactKind.COMPENSATION, EventRole.FUNDER, EventRole.RECIPIENT),
        )
    )


def _normalized_pair(
    fact_kind: FactKind,
    left_role: EventRole,
    right_role: EventRole,
) -> tuple[FactKind, EventRole, EventRole]:
    if left_role.value <= right_role.value:
        return fact_kind, left_role, right_role
    return fact_kind, right_role, left_role
