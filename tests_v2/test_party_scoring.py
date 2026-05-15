from __future__ import annotations

from pipeline_v2.candidates import EntityCandidate, PartyAffiliationCandidate
from pipeline_v2.ids import (
    EntityCandidateId,
    EvidenceId,
    FactCandidateId,
    MentionId,
    ProducerId,
    SentenceId,
)
from pipeline_v2.nlp import EvidenceSpan, Mention, Sentence, Span
from pipeline_v2.orchestrator import V2Orchestrator
from pipeline_v2.store import ExtractionStore
from pipeline_v2.types import EntityKind, GroundingKind, MentionKind


def test_party_scorer_separates_noisy_candidate_from_final_reliability() -> None:
    store = ExtractionStore()
    sentence_id = SentenceId("sentence-1")
    sentence_text = "Wojciech Wilk z PO oraz Krzysztof Staruch, bezpartyjny, rozmawiali."
    store.add_sentence(
        Sentence(
            id=sentence_id,
            sentence_index=0,
            paragraph_index=0,
            text=sentence_text,
            span=Span(0, len(sentence_text)),
        )
    )
    evidence_id = EvidenceId("evidence-1")
    store.add_evidence(
        EvidenceSpan(
            id=evidence_id,
            text=sentence_text,
            span=Span(0, len(sentence_text)),
            sentence_id=sentence_id,
            paragraph_index=0,
        )
    )
    person_mention_id = MentionId("mention-staruch")
    party_mention_id = MentionId("mention-po")
    store.add_mention(
        Mention(
            id=person_mention_id,
            text="Krzysztof Staruch",
            kind=MentionKind.NER,
            evidence_id=evidence_id,
            sentence_id=sentence_id,
        )
    )
    store.add_mention(
        Mention(
            id=party_mention_id,
            text="PO",
            kind=MentionKind.NER,
            evidence_id=evidence_id,
            sentence_id=sentence_id,
        )
    )
    subject_id = store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("staruch"),
            kind=EntityKind.PERSON,
            mention_ids=(person_mention_id,),
            canonical_hint="Krzysztof Staruch",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    party_id = store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("po"),
            kind=EntityKind.POLITICAL_PARTY,
            mention_ids=(party_mention_id,),
            canonical_hint="Platforma Obywatelska",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )

    candidate = PartyAffiliationCandidate(
        id=FactCandidateId("party-candidate"),
        subject_entity_id=subject_id,
        party_entity_id=party_id,
        evidence_ids=(evidence_id,),
        source=ProducerId("test"),
    )
    store.add_fact_candidate(candidate)
    result = V2Orchestrator(store).assess(party_affiliations=(candidate,))
    assessed = result.party_affiliation_assessments[0]
    assessment = assessed.assessment

    assert assessment.score < 0.5
    assert any(signal.name == "explicit_nonparty_context" for signal in assessment.negative_signals)
