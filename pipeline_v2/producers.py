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
from pipeline_v2.types import (
    ConflictingPartyAffiliationSignal,
    DirectPrepositionalAttachmentSignal,
    EntityKind,
    ExplicitNonPartyContextSignal,
    FactArgumentRole,
    FactKind,
    GroundingKind,
    PartyAliasMatchSignal,
    SameNameContradictionSignal,
    SameNameContrastContextSignal,
    Signal,
)


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
        signals: list[Signal] = [PartyAliasMatchSignal()]
        if direct_attachment:
            signals.append(DirectPrepositionalAttachmentSignal())
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
                signals.append(ExplicitNonPartyContextSignal())
            if "nie mylić" in evidence_text or "nie mylic" in evidence_text:
                signals.append(SameNameContradictionSignal())
                signals.append(SameNameContrastContextSignal())
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

    def _find_parties_for_entity(
        self, store: ExtractionStore, entity_id: EntityCandidateId
    ) -> set[str]:
        parties: set[str] = set()
        for candidate in store.fact_candidates.values():
            record = candidate.to_fact_record()
            if record.kind != FactKind.PARTY_AFFILIATION:
                continue
            arguments = tuple(argument.to_json() for argument in record.arguments)
            subject = next(
                (
                    argument["entity_id"]
                    for argument in arguments
                    if argument["role"] == FactArgumentRole.SUBJECT.value
                ),
                None,
            )
            if subject != str(entity_id):
                continue
            party_id = next(
                (
                    argument["entity_id"]
                    for argument in arguments
                    if argument["role"] == FactArgumentRole.OBJECT.value
                ),
                None,
            )
            if party_id is None:
                continue
            party_entity = store.entity_candidates.get(EntityCandidateId(party_id))
            if party_entity is not None and party_entity.canonical_hint is not None:
                parties.add(party_entity.canonical_hint.casefold())
        return parties

    def enrich_resolution_proposal(
        self,
        store: ExtractionStore,
        proposal: EntityResolutionProposal,
    ) -> EntityResolutionProposal:
        context_signals = list(self.signals_for_evidence_ids(store, proposal.evidence_ids))

        left_parties = self._find_parties_for_entity(store, proposal.left_entity_id)
        right_parties = self._find_parties_for_entity(store, proposal.right_entity_id)

        if left_parties and right_parties and left_parties.isdisjoint(right_parties):
            left_hint = next(iter(left_parties))
            right_hint = next(iter(right_parties))
            context_signals.append(
                ConflictingPartyAffiliationSignal(
                    left_party_hint=left_hint, right_party_hint=right_hint
                )
            )

        return EntityResolutionProposal(
            left_entity_id=proposal.left_entity_id,
            right_entity_id=proposal.right_entity_id,
            evidence_ids=proposal.evidence_ids,
            retrieval_signals=proposal.retrieval_signals,
            context_signals=tuple(context_signals),
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
