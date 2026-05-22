from __future__ import annotations

from pipeline_v2.candidates import (
    Assessment,
    EntityContextProposal,
    EntityResolutionProposal,
    ReferenceResolutionProposal,
)
from pipeline_v2.ids import ScorerId
from pipeline_v2.store import ExtractionStore
from pipeline_v2.types import (
    CanonicalHintMatchSignal,
    ConflictingPartyAffiliationSignal,
    CoreferenceProviderLinkSignal,
    DescriptorPersonCandidateSignal,
    FullNameReuseMatchSignal,
    LemmaMatchSignal,
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
                case LemmaMatchSignal():
                    score += 0.4
                case DescriptorPersonCandidateSignal(sentence_distance=d):
                    score += 0.24
                    score += max(0.0, 0.12 - 0.06 * d)
                case NearbyPersonCandidateSignal():
                    score += 0.12

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


class EntityContextScorer:
    """Turn lemma/hint retrieval signals from a `LexicalEntityContextProposal`
    into a prior `Assessment` for the corresponding `EntityContext` inference
    variable.  A canonical-hint hit is the strongest cue; multiple lemma hits
    raise confidence; a single lemma is moderate."""

    scorer_id = ScorerId("lexical_entity_context_scorer_v2")

    def score(self, proposal: EntityContextProposal) -> Assessment:
        positive = list(proposal.retrieval_signals)
        has_canonical_hint = False
        lemma_signal_count = 0
        for signal in positive:
            match signal:
                case CanonicalHintMatchSignal():
                    has_canonical_hint = True
                case _:
                    lemma_signal_count += 1
        if has_canonical_hint:
            base = 0.95
        elif lemma_signal_count >= 2:
            base = 0.9
        elif lemma_signal_count == 1:
            base = 0.75
        else:
            base = 0.5
        score = max(0.0, min(1.0, round(base, 3)))
        return Assessment(
            score=score,
            positive_signals=tuple(positive),
            negative_signals=(),
            scorer_id=self.scorer_id,
            explanation=(
                "entity context prior scored from canonical-hint and lemma retrieval signals"
            ),
        )
