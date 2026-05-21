from __future__ import annotations

from pipeline_v2.candidates import (
    Assessment,
    EntityResolutionProposal,
    ReferenceResolutionProposal,
)
from pipeline_v2.ids import ScorerId
from pipeline_v2.store import ExtractionStore
from pipeline_v2.types import (
    ConflictingPartyAffiliationSignal,
    CoreferenceProviderLinkSignal,
    FullNameReuseMatchSignal,
    NearbyPersonCandidateSignal,
    SameNameContradictionSignal,
    SignalPolarity,
    SurnameBaseMatchSignal,
    ThirdPersonPronounSignal,
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
                case ConflictingPartyAffiliationSignal():
                    score -= 0.5
        return Assessment(
            score=max(0.0, min(1.0, round(score, 3))),
            positive_signals=tuple(positive),
            negative_signals=tuple(negative),
            scorer_id=self.scorer_id,
            explanation="entity resolution scored from retrieval and contradiction signals",
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
