from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pipeline_v2.types import (
    AntiCorruptionInvestigationLemmaSignal,
    AntiCorruptionReferralLemmaSignal,
    AppointerContextSignal,
    AppointmentLemmaSignal,
    CandidacyContextSignal,
    CollectivePartyContextSignal,
    CompensationLemmaSignal,
    ControllerContextSignal,
    DependencyObjectSignal,
    DependencySubjectSignal,
    DirectPrepositionalAttachmentSignal,
    DiscourseOrganizationSignal,
    DismissalLemmaSignal,
    EmbeddedInOrganizationNameSignal,
    EmploymentContractFormSignal,
    ExplicitNonPartyContextSignal,
    ExplicitPatronageLemmaSignal,
    FactKind,
    FundingLemmaSignal,
    LocalActorSignal,
    LocalInstitutionSignal,
    LocalObjectSignal,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    LocalSubjectSignal,
    LocalTargetSignal,
    MicroAmountSignal,
    MoneyAmountSignal,
    NamedKinshipLemmaSignal,
    NominalKinshipSignal,
    OversightInstitutionSignal,
    PartyAliasMatchSignal,
    PartyOrganizationSignal,
    PartyProfileLemmaSignal,
    PossessiveKinshipSignal,
    PrepositionalOrganizationSignal,
    ProxyFamilyEntitySignal,
    PseudonymousSourceSignal,
    PublicContractLemmaSignal,
    PublicEmploymentLemmaSignal,
    RelationshipDetailSignal,
    Signal,
    SignalPolarity,
    WeakSyntacticBindingSignal,
    WindowFallbackSignal,
    WindowOrganizationSignal,
    WindowPersonSignal,
    WindowRoleSignal,
)


@dataclass(frozen=True, slots=True)
class FactPrior:
    score: float
    positive_signals: tuple[Signal, ...]
    negative_signals: tuple[Signal, ...]


class FactPriorPolicy(Protocol):
    def applies_to(self, kind: FactKind) -> bool: ...

    def base_score(self, kind: FactKind) -> float: ...

    def positive_delta(self, signal: Signal) -> float: ...

    def negative_delta(self, signal: Signal, kind: FactKind) -> float: ...


class BaseFactPriorPolicy:
    kinds: frozenset[FactKind] = frozenset()
    kind_bonus: float = 0.0

    def applies_to(self, kind: FactKind) -> bool:
        return kind in self.kinds

    def base_score(self, kind: FactKind) -> float:
        _ = kind
        return 0.2 + self.kind_bonus

    def positive_delta(self, signal: Signal) -> float:
        match signal:
            case MoneyAmountSignal():
                return 0.25
            case FundingLemmaSignal() | PublicContractLemmaSignal() | CompensationLemmaSignal():
                return 0.25
            case AppointmentLemmaSignal() | DismissalLemmaSignal():
                return 0.25
            case LocalPersonSignal():
                return 0.15
            case WindowPersonSignal():
                return 0.1
            case LocalOrganizationSignal():
                return 0.1
            case WindowOrganizationSignal():
                return 0.08
            case LocalRoleSignal():
                return 0.05
            case WindowRoleSignal():
                return 0.04
            case PartyAliasMatchSignal():
                return 0.2
            case DirectPrepositionalAttachmentSignal():
                return 0.25
            case PartyProfileLemmaSignal():
                return 0.25
            case CandidacyContextSignal():
                return 0.1
            case CollectivePartyContextSignal():
                return 0.05
            case AntiCorruptionReferralLemmaSignal():
                return 0.25
            case AntiCorruptionInvestigationLemmaSignal():
                return 0.25
            case OversightInstitutionSignal():
                return 0.15
            case LocalActorSignal():
                return 0.1
            case LocalTargetSignal():
                return 0.1
            case LocalInstitutionSignal():
                return 0.05
            case PublicEmploymentLemmaSignal():
                return 0.25
            case EmploymentContractFormSignal():
                return 0.1
            case ProxyFamilyEntitySignal():
                return 0.25
            case RelationshipDetailSignal():
                return 0.15
            case NamedKinshipLemmaSignal() | NominalKinshipSignal():
                return 0.25
            case ExplicitPatronageLemmaSignal():
                return 0.2
            case LocalSubjectSignal():
                return 0.1
            case LocalObjectSignal():
                return 0.1
            case DependencySubjectSignal():
                return 0.18
            case DependencyObjectSignal():
                return 0.18
            case PrepositionalOrganizationSignal():
                return 0.12
            case PossessiveKinshipSignal():
                return 0.15
            case WindowFallbackSignal(distance=distance):
                return max(0.0, 0.08 - 0.02 * distance)
        return 0.0

    def negative_delta(self, signal: Signal, kind: FactKind) -> float:
        match signal:
            case ExplicitNonPartyContextSignal():
                return -0.35
            case MicroAmountSignal():
                if kind == FactKind.COMPENSATION:
                    return -0.6
            case PartyOrganizationSignal():
                return -0.6
            case DiscourseOrganizationSignal():
                return -0.15
            case EmbeddedInOrganizationNameSignal():
                return -0.6
            case WeakSyntacticBindingSignal():
                return -0.35
            case AppointerContextSignal():
                return -0.6
            case ControllerContextSignal():
                return -0.55
            case PseudonymousSourceSignal():
                return -0.55
        return 0.0


class PublicMoneyPriorPolicy(BaseFactPriorPolicy):
    kinds = frozenset({FactKind.FUNDING, FactKind.PUBLIC_CONTRACT, FactKind.COMPENSATION})
    kind_bonus = 0.15


class GovernancePriorPolicy(BaseFactPriorPolicy):
    kinds = frozenset({FactKind.GOVERNANCE_APPOINTMENT, FactKind.GOVERNANCE_DISMISSAL})
    kind_bonus = 0.15


class PoliticalContextPriorPolicy(BaseFactPriorPolicy):
    kinds = frozenset({FactKind.PARTY_AFFILIATION, FactKind.POLITICAL_SUPPORT})
    kind_bonus = 0.15


class AntiCorruptionPriorPolicy(BaseFactPriorPolicy):
    kinds = frozenset({FactKind.ANTI_CORRUPTION_REFERRAL, FactKind.ANTI_CORRUPTION_INVESTIGATION})
    kind_bonus = 0.15


class PublicEmploymentPriorPolicy(BaseFactPriorPolicy):
    kinds = frozenset({FactKind.PUBLIC_EMPLOYMENT})
    kind_bonus = 0.15


class PersonalTiePriorPolicy(BaseFactPriorPolicy):
    kinds = frozenset({FactKind.PERSONAL_OR_POLITICAL_TIE})
    kind_bonus = 0.15


class DefaultPriorPolicy(BaseFactPriorPolicy):
    def applies_to(self, kind: FactKind) -> bool:
        _ = kind
        return True


class FactPriorPolicyRegistry:
    def __init__(self, policies: tuple[FactPriorPolicy, ...] | None = None) -> None:
        self.policies = policies or (
            PublicMoneyPriorPolicy(),
            GovernancePriorPolicy(),
            PoliticalContextPriorPolicy(),
            AntiCorruptionPriorPolicy(),
            PublicEmploymentPriorPolicy(),
            PersonalTiePriorPolicy(),
            DefaultPriorPolicy(),
        )

    def prior_for_kind(
        self,
        kind: FactKind,
        signals: tuple[Signal, ...],
    ) -> FactPrior:
        policy = self._policy_for(kind)
        positive = tuple(signal for signal in signals if signal.polarity == SignalPolarity.POSITIVE)
        negative = tuple(signal for signal in signals if signal.polarity == SignalPolarity.NEGATIVE)
        score = policy.base_score(kind)
        for signal in positive:
            score += policy.positive_delta(signal)
        for signal in negative:
            score += policy.negative_delta(signal, kind)
        return FactPrior(
            score=max(0.0, min(1.0, round(score, 3))),
            positive_signals=positive,
            negative_signals=negative,
        )

    def _policy_for(self, kind: FactKind) -> FactPriorPolicy:
        for policy in self.policies:
            if policy.applies_to(kind):
                return policy
        raise ValueError(f"no fact prior policy registered for {kind.value}")
