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
from pipeline_v2.types import FactKind, SignalPolarity


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
        if any(signal.name == "same_surname_base" for signal in proposal.retrieval_signals):
            score += 0.2
        distance_signals = [
            signal.name
            for signal in proposal.retrieval_signals
            if signal.name.startswith("paragraph_distance:")
        ]
        if distance_signals:
            distance = int(distance_signals[0].split(":", 1)[1])
            score += max(0.0, 0.2 - 0.08 * distance)
        if any(signal.name == "same_name_contradiction" for signal in negative):
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
        if any(signal.name == "party_alias_match" for signal in candidate.signals):
            score += 0.25
        if any(signal.name == "direct_prepositional_attachment" for signal in candidate.signals):
            score += 0.25
        if any(signal.name == "explicit_nonparty_context" for signal in negative):
            score -= 0.35
        if any(signal.name == "same_name_contrast_context" for signal in negative):
            score -= 0.2
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
        if any(signal.name == "coreference_provider_link" for signal in positive):
            score += 0.5
        if any(signal.name == "third_person_pronoun" for signal in positive):
            score += 0.1
        if any(signal.name == "nearby_person_candidate" for signal in positive):
            score += 0.2
        if any(signal.name == "same_name_contradiction" for signal in negative):
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
        if any(signal.name == "money_amount" for signal in positive):
            score += 0.25
        if any(
            signal.name
            in {
                "funding_lemma",
                "public_contract_lemma",
                "compensation_lemma",
            }
            for signal in positive
        ):
            score += 0.25
        if any(signal.name in {"appointment_lemma", "dismissal_lemma"} for signal in positive):
            score += 0.25
        if any(signal.name == "sentence_local_person" for signal in positive):
            score += 0.15
        if any(signal.name == "discourse_window_person" for signal in positive):
            score += 0.1
        if any(signal.name == "sentence_local_organization" for signal in positive):
            score += 0.1
        if any(signal.name == "discourse_window_organization" for signal in positive):
            score += 0.08
        if any(signal.name == "sentence_local_role" for signal in positive):
            score += 0.05
        if any(signal.name == "discourse_window_role" for signal in positive):
            score += 0.04
        if any(signal.name == "party_alias_match" for signal in positive):
            score += 0.2
        if any(signal.name == "direct_prepositional_attachment" for signal in positive):
            score += 0.25
        if any(signal.name == "party_profile_lemma" for signal in positive):
            score += 0.25
        if any(signal.name == "candidacy_context" for signal in positive):
            score += 0.1
        if any(signal.name == "collective_party_context" for signal in positive):
            score += 0.05
        if any(signal.name == "anti_corruption_referral_lemma" for signal in positive):
            score += 0.25
        if any(signal.name == "anti_corruption_investigation_lemma" for signal in positive):
            score += 0.25
        if any(signal.name == "oversight_institution" for signal in positive):
            score += 0.15
        if any(signal.name == "sentence_local_actor" for signal in positive):
            score += 0.1
        if any(signal.name == "sentence_local_target" for signal in positive):
            score += 0.1
        if any(signal.name == "sentence_local_institution" for signal in positive):
            score += 0.05
        if any(signal.name == "public_employment_lemma" for signal in positive):
            score += 0.25
        if any(signal.name == "employment_contract_form" for signal in positive):
            score += 0.1
        if any(signal.name == "proxy_family_entity" for signal in positive):
            score += 0.25
        if any(signal.name == "relationship_detail" for signal in positive):
            score += 0.15
        if any(signal.name == "named_kinship_lemma" for signal in positive):
            score += 0.25
        if any(signal.name == "explicit_patronage_lemma" for signal in positive):
            score += 0.2
        if any(signal.name == "sentence_local_subject" for signal in positive):
            score += 0.1
        if any(signal.name == "sentence_local_object" for signal in positive):
            score += 0.1
        if any(signal.name == "explicit_nonparty_context" for signal in negative):
            score -= 0.35
        return Assessment(
            score=max(0.0, min(1.0, round(score, 3))),
            positive_signals=tuple(positive),
            negative_signals=tuple(negative),
            scorer_id=self.scorer_id,
            explanation="fact candidate scored from typed fact kind and evidence signals",
        )
