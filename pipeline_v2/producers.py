from __future__ import annotations

from pipeline_v2.candidates import (
    EntityCandidate,
    EntityResolutionProposal,
    FullPersonNameKey,
    PartyAffiliationCandidate,
    ReferenceResolutionProposal,
)
from pipeline_v2.ids import EntityCandidateId, EvidenceId, FactCandidateId, MentionId, ProducerId
from pipeline_v2.store import ExtractionStore
from pipeline_v2.types import EntityKind, GroundingKind, Signal, negative_signal, positive_signal


class SimpleEntityCandidateProducer:
    """Small deterministic producer used by the first v2 tests.

    Real spaCy/Stanza/Morfeusz-backed producers should emit the same typed
    records, but this class keeps the skeleton executable without coupling v2
    tests to heavy NLP model loading.
    """

    producer_id = ProducerId("simple_entity_candidate_producer")

    def add_full_person(
        self,
        store: ExtractionStore,
        *,
        candidate_id: EntityCandidateId,
        mention_ids: tuple[MentionId, ...],
        given_name_lemma: str,
        surname_base: str,
        canonical_hint: str,
    ) -> EntityCandidateId:
        key = FullPersonNameKey(given_name_lemma=given_name_lemma, surname_base=surname_base)
        return store.add_entity_candidate(
            EntityCandidate(
                id=candidate_id,
                kind=EntityKind.PERSON,
                mention_ids=mention_ids,
                canonical_hint=canonical_hint,
                grounding=GroundingKind.OBSERVED,
                source=self.producer_id,
                blocking_key=key,
                reuse_key=key,
            )
        )

    def add_surname_only_person(
        self,
        store: ExtractionStore,
        *,
        candidate_id: EntityCandidateId,
        mention_ids: tuple[MentionId, ...],
        canonical_hint: str,
    ) -> EntityCandidateId:
        return store.add_entity_candidate(
            EntityCandidate(
                id=candidate_id,
                kind=EntityKind.PERSON,
                mention_ids=mention_ids,
                canonical_hint=canonical_hint,
                grounding=GroundingKind.OBSERVED,
                source=self.producer_id,
                blocking_key=None,
                reuse_key=None,
            )
        )


class SimplePartyAffiliationProducer:
    producer_id = ProducerId("simple_party_affiliation_producer")

    def add_candidate(
        self,
        store: ExtractionStore,
        *,
        candidate_id: FactCandidateId,
        subject_id: EntityCandidateId,
        party_id: EntityCandidateId,
        evidence_ids: tuple[EvidenceId, ...],
        direct_attachment: bool = False,
    ) -> FactCandidateId:
        signals = [positive_signal("party_alias_match")]
        if direct_attachment:
            signals.append(positive_signal("direct_prepositional_attachment"))
        return store.add_fact_candidate(
            PartyAffiliationCandidate(
                id=candidate_id,
                subject_entity_id=subject_id,
                party_entity_id=party_id,
                evidence_ids=evidence_ids,
                source=self.producer_id,
                signals=tuple(signals),
            )
        )


class EvidenceSignalProducer:
    producer_id = ProducerId("evidence_signal_producer")

    def signals_for_evidence_ids(
        self,
        store: ExtractionStore,
        evidence_ids: tuple[EvidenceId, ...],
    ) -> tuple[Signal, ...]:
        signals: list[Signal] = []
        for evidence_id in evidence_ids:
            evidence_text = store.evidence[evidence_id].text.casefold()
            if "bezpartyjny" in evidence_text:
                signals.append(negative_signal("explicit_nonparty_context"))
            if "nie mylić" in evidence_text or "nie mylic" in evidence_text:
                signals.append(negative_signal("same_name_contradiction"))
                signals.append(negative_signal("same_name_contrast_context"))
        return tuple(dict.fromkeys(signals))

    def enrich_party_affiliation(
        self,
        store: ExtractionStore,
        candidate: PartyAffiliationCandidate,
    ) -> PartyAffiliationCandidate:
        signals = (
            *candidate.signals,
            *self.signals_for_evidence_ids(store, candidate.evidence_ids),
        )
        return PartyAffiliationCandidate(
            id=candidate.id,
            subject_entity_id=candidate.subject_entity_id,
            party_entity_id=candidate.party_entity_id,
            evidence_ids=candidate.evidence_ids,
            source=candidate.source,
            signals=tuple(dict.fromkeys(signals)),
        )

    def enrich_resolution_proposal(
        self,
        store: ExtractionStore,
        proposal: EntityResolutionProposal,
    ) -> EntityResolutionProposal:
        return EntityResolutionProposal(
            left_entity_id=proposal.left_entity_id,
            right_entity_id=proposal.right_entity_id,
            evidence_ids=proposal.evidence_ids,
            retrieval_signals=proposal.retrieval_signals,
            context_signals=self.signals_for_evidence_ids(store, proposal.evidence_ids),
        )

    def enrich_reference_resolution_proposal(
        self,
        store: ExtractionStore,
        proposal: ReferenceResolutionProposal,
    ) -> ReferenceResolutionProposal:
        return ReferenceResolutionProposal(
            reference_id=proposal.reference_id,
            candidate_entity_id=proposal.candidate_entity_id,
            evidence_ids=proposal.evidence_ids,
            retrieval_signals=proposal.retrieval_signals,
            context_signals=self.signals_for_evidence_ids(store, proposal.evidence_ids),
        )
