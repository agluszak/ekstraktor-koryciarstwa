from __future__ import annotations

from pipeline_v2.candidates import (
    Assessment,
    EntityResolutionProposal,
    FactCandidateRecord,
    PartyAffiliationCandidate,
    ReferenceResolutionProposal,
)
from pipeline_v2.ids import ScorerId
from pipeline_v2.store import ExtractionStore
from pipeline_v2.types import (
    AntiCorruptionInvestigationLemmaSignal,
    AntiCorruptionReferralLemmaSignal,
    AppointmentLemmaSignal,
    CandidacyContextSignal,
    CollectivePartyContextSignal,
    CompensationLemmaSignal,
    CoreferenceProviderLinkSignal,
    DirectPrepositionalAttachmentSignal,
    DismissalLemmaSignal,
    EmploymentContractFormSignal,
    ExplicitNonPartyContextSignal,
    ExplicitPatronageLemmaSignal,
    FactKind,
    FullNameReuseMatchSignal,
    FundingLemmaSignal,
    LocalActorSignal,
    LocalInstitutionSignal,
    LocalObjectSignal,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    LocalSubjectSignal,
    LocalTargetSignal,
    MoneyAmountSignal,
    NamedKinshipLemmaSignal,
    NearbyPersonCandidateSignal,
    OversightInstitutionSignal,
    PartyAliasMatchSignal,
    PartyProfileLemmaSignal,
    ProxyFamilyEntitySignal,
    PublicContractLemmaSignal,
    PublicEmploymentLemmaSignal,
    RelationshipDetailSignal,
    SameNameContradictionSignal,
    SignalPolarity,
    SurnameBaseMatchSignal,
    ThirdPersonPronounSignal,
    WindowOrganizationSignal,
    WindowPersonSignal,
    WindowRoleSignal,
)


class EntityResolutionScorer:
    scorer_id = ScorerId("entity_resolution_scorer_v2")

    def __init__(self, store: ExtractionStore) -> None:
        self.store = store

    def score(self, proposal: EntityResolutionProposal) -> Assessment:
        positive = list(proposal.retrieval_signals)
        negative = [
            signal
            for signal in proposal.context_signals
            if signal.polarity == SignalPolarity.NEGATIVE
        ]
        score = 0.35
        for signal in proposal.retrieval_signals:
            match signal:
                case FullNameReuseMatchSignal():
                    score += 0.55
                case SurnameBaseMatchSignal(distance=d):
                    score += 0.2
                    score += max(0.0, 0.15 - 0.05 * d)

        for signal in negative:
            match signal:
                case SameNameContradictionSignal():
                    score -= 0.45
        return Assessment(
            score=max(0.0, min(1.0, round(score, 3))),
            positive_signals=tuple(positive),
            negative_signals=tuple(negative),
            scorer_id=self.scorer_id,
            explanation="entity resolution scored from retrieval and contradiction signals",
        )


class PartyAffiliationScorer:
    scorer_id = ScorerId("party_affiliation_scorer_v2")

    def __init__(self, store: ExtractionStore) -> None:
        self.store = store

    def score(self, candidate: PartyAffiliationCandidate) -> Assessment:
        positive = [
            signal for signal in candidate.signals if signal.polarity == SignalPolarity.POSITIVE
        ]
        negative = [
            signal for signal in candidate.signals if signal.polarity == SignalPolarity.NEGATIVE
        ]
        score = 0.35
        for signal in candidate.signals:
            match signal:
                case PartyAliasMatchSignal():
                    score += 0.25
                case DirectPrepositionalAttachmentSignal():
                    score += 0.25

        for signal in negative:
            match signal:
                case ExplicitNonPartyContextSignal():
                    score -= 0.35
        return Assessment(
            score=max(0.0, min(1.0, round(score, 3))),
            positive_signals=tuple(positive),
            negative_signals=tuple(negative),
            scorer_id=self.scorer_id,
            explanation=(
                "party affiliation scored from syntactic, lexical, and contradiction signals"
            ),
        )


class ReferenceResolutionScorer:
    scorer_id = ScorerId("reference_resolution_scorer_v2")

    def __init__(self, store: ExtractionStore) -> None:
        self.store = store

    def score(self, proposal: ReferenceResolutionProposal) -> Assessment:
        positive = [
            signal
            for signal in proposal.retrieval_signals
            if signal.polarity == SignalPolarity.POSITIVE
        ]
        negative = [
            signal
            for signal in proposal.context_signals
            if signal.polarity == SignalPolarity.NEGATIVE
        ]
        score = 0.25
        for signal in positive:
            match signal:
                case CoreferenceProviderLinkSignal():
                    score += 0.5
                case ThirdPersonPronounSignal():
                    score += 0.1
                case NearbyPersonCandidateSignal():
                    score += 0.2

        for signal in negative:
            match signal:
                case SameNameContradictionSignal():
                    score -= 0.35
        return Assessment(
            score=max(0.0, min(1.0, round(score, 3))),
            positive_signals=tuple(positive),
            negative_signals=tuple(negative),
            scorer_id=self.scorer_id,
            explanation="reference resolution scored from typed provider and context signals",
        )


class FactRecordScorer:
    scorer_id = ScorerId("fact_record_scorer_v2")
    _public_money_kinds = frozenset(
        {
            FactKind.FUNDING,
            FactKind.PUBLIC_CONTRACT,
            FactKind.COMPENSATION,
        }
    )
    _governance_kinds = frozenset(
        {
            FactKind.GOVERNANCE_APPOINTMENT,
            FactKind.GOVERNANCE_DISMISSAL,
        }
    )
    _political_context_kinds = frozenset(
        {
            FactKind.PARTY_AFFILIATION,
            FactKind.POLITICAL_SUPPORT,
        }
    )
    _anti_corruption_kinds = frozenset(
        {
            FactKind.ANTI_CORRUPTION_REFERRAL,
            FactKind.ANTI_CORRUPTION_INVESTIGATION,
        }
    )
    _public_employment_kinds = frozenset({FactKind.PUBLIC_EMPLOYMENT})
    _tie_kinds = frozenset({FactKind.PERSONAL_OR_POLITICAL_TIE})

    def __init__(self, store: ExtractionStore) -> None:
        self.store = store

    def score(self, record: FactCandidateRecord) -> Assessment:
        positive = [
            signal for signal in record.signals if signal.polarity == SignalPolarity.POSITIVE
        ]
        negative = [
            signal for signal in record.signals if signal.polarity == SignalPolarity.NEGATIVE
        ]
        score = 0.2
        if record.kind in self._public_money_kinds:
            score += 0.15
        if record.kind in self._governance_kinds:
            score += 0.15
        if record.kind in self._political_context_kinds:
            score += 0.15
        if record.kind in self._anti_corruption_kinds:
            score += 0.15
        if record.kind in self._public_employment_kinds:
            score += 0.15
        if record.kind in self._tie_kinds:
            score += 0.15

        for signal in positive:
            match signal:
                case MoneyAmountSignal():
                    score += 0.25
                case FundingLemmaSignal() | PublicContractLemmaSignal() | CompensationLemmaSignal():
                    score += 0.25
                case AppointmentLemmaSignal() | DismissalLemmaSignal():
                    score += 0.25
                case LocalPersonSignal():
                    score += 0.15
                case WindowPersonSignal():
                    score += 0.1
                case LocalOrganizationSignal():
                    score += 0.1
                case WindowOrganizationSignal():
                    score += 0.08
                case LocalRoleSignal():
                    score += 0.05
                case WindowRoleSignal():
                    score += 0.04
                case PartyAliasMatchSignal():
                    score += 0.2
                case DirectPrepositionalAttachmentSignal():
                    score += 0.25
                case PartyProfileLemmaSignal():
                    score += 0.25
                case CandidacyContextSignal():
                    score += 0.1
                case CollectivePartyContextSignal():
                    score += 0.05
                case AntiCorruptionReferralLemmaSignal():
                    score += 0.25
                case AntiCorruptionInvestigationLemmaSignal():
                    score += 0.25
                case OversightInstitutionSignal():
                    score += 0.15
                case LocalActorSignal():
                    score += 0.1
                case LocalTargetSignal():
                    score += 0.1
                case LocalInstitutionSignal():
                    score += 0.05
                case PublicEmploymentLemmaSignal():
                    score += 0.25
                case EmploymentContractFormSignal():
                    score += 0.1
                case ProxyFamilyEntitySignal():
                    score += 0.25
                case RelationshipDetailSignal():
                    score += 0.15
                case NamedKinshipLemmaSignal():
                    score += 0.25
                case ExplicitPatronageLemmaSignal():
                    score += 0.2
                case LocalSubjectSignal():
                    score += 0.1
                case LocalObjectSignal():
                    score += 0.1

        for signal in negative:
            match signal:
                case ExplicitNonPartyContextSignal():
                    score -= 0.35
        return Assessment(
            score=max(0.0, min(1.0, round(score, 3))),
            positive_signals=tuple(positive),
            negative_signals=tuple(negative),
            scorer_id=self.scorer_id,
            explanation="fact candidate scored from typed fact kind and evidence signals",
        )
