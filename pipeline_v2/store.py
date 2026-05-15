from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from pipeline_v2.candidates import (
    EntityBlockingKey,
    EntityCandidate,
    EntityResolutionClaim,
    FactCandidate,
    FullPersonNameKey,
    OrganizationAcronymKey,
    ReferenceResolutionClaim,
)
from pipeline_v2.ids import (
    EntityCandidateId,
    EvidenceId,
    FactCandidateId,
    MentionId,
    ResolutionClaimId,
    SentenceId,
    TokenId,
)
from pipeline_v2.nlp import DependencyArc, EvidenceSpan, Mention, ReferenceMention, Sentence, Token
from pipeline_v2.types import EntityKind


class ExtractionStore:
    """Typed append-oriented store for v2 extraction records.

    The store owns only stable, cross-cutting indexes. Specialized retrieval
    logic belongs in retriever classes, not as more store fields.
    """

    def __init__(self) -> None:
        self.sentences: dict[SentenceId, Sentence] = {}
        self.tokens: dict[TokenId, Token] = {}
        self.dependency_arcs_by_sentence_id: dict[SentenceId, list[DependencyArc]] = defaultdict(
            list
        )
        self.evidence: dict[EvidenceId, EvidenceSpan] = {}
        self.mentions: dict[MentionId, Mention] = {}
        self.references: dict[MentionId, ReferenceMention] = {}
        self.entity_candidates: dict[EntityCandidateId, EntityCandidate] = {}
        self.fact_candidates: dict[FactCandidateId, FactCandidate] = {}
        self.resolution_claims: dict[ResolutionClaimId, EntityResolutionClaim] = {}
        self.reference_resolution_claims: dict[ResolutionClaimId, ReferenceResolutionClaim] = {}

        self.mention_ids_by_sentence_id: dict[SentenceId, set[MentionId]] = defaultdict(set)
        self.reference_ids_by_sentence_id: dict[SentenceId, set[MentionId]] = defaultdict(set)
        self.entity_ids_by_mention_id: dict[MentionId, set[EntityCandidateId]] = defaultdict(set)
        self.entity_ids_by_reference_id: dict[MentionId, set[EntityCandidateId]] = defaultdict(set)
        self.entity_ids_by_blocking_key: dict[EntityBlockingKey, set[EntityCandidateId]] = (
            defaultdict(set)
        )
        self.entity_id_by_reuse_key: dict[FullPersonNameKey, EntityCandidateId] = {}
        self.fact_ids_by_entity_id: dict[EntityCandidateId, set[FactCandidateId]] = defaultdict(set)
        self.resolution_ids_by_entity_id: dict[EntityCandidateId, set[ResolutionClaimId]] = (
            defaultdict(set)
        )
        self.reference_resolution_ids_by_reference_id: dict[MentionId, set[ResolutionClaimId]] = (
            defaultdict(set)
        )

    def add_sentence(self, sentence: Sentence) -> SentenceId:
        self.sentences[sentence.id] = sentence
        return sentence.id

    def add_token(self, token: Token) -> TokenId:
        self.tokens[token.id] = token
        return token.id

    def add_dependency_arc(self, sentence_id: SentenceId, arc: DependencyArc) -> None:
        self.dependency_arcs_by_sentence_id[sentence_id].append(arc)

    def dependency_arcs_for_sentence(self, sentence_id: SentenceId) -> tuple[DependencyArc, ...]:
        return tuple(self.dependency_arcs_by_sentence_id.get(sentence_id, ()))

    def add_evidence(self, evidence: EvidenceSpan) -> EvidenceId:
        self.evidence[evidence.id] = evidence
        return evidence.id

    def add_mention(self, mention: Mention) -> MentionId:
        self.mentions[mention.id] = mention
        self.mention_ids_by_sentence_id[mention.sentence_id].add(mention.id)
        return mention.id

    def add_reference(self, reference: ReferenceMention) -> MentionId:
        self.references[reference.id] = reference
        self.reference_ids_by_sentence_id[reference.sentence_id].add(reference.id)
        return reference.id

    def add_entity_candidate(self, candidate: EntityCandidate) -> EntityCandidateId:
        if candidate.reuse_key is not None:
            existing_id = self.entity_id_by_reuse_key.get(candidate.reuse_key)
            if existing_id is not None:
                existing = self.entity_candidates[existing_id]
                merged_mentions = tuple(
                    dict.fromkeys([*existing.mention_ids, *candidate.mention_ids])
                )
                merged_references = tuple(
                    dict.fromkeys([*existing.reference_ids, *candidate.reference_ids])
                )
                self.entity_candidates[existing_id] = replace(
                    existing,
                    mention_ids=merged_mentions,
                    reference_ids=merged_references,
                    canonical_hint=existing.canonical_hint or candidate.canonical_hint,
                )
                for mention_id in candidate.mention_ids:
                    self.entity_ids_by_mention_id[mention_id].add(existing_id)
                for reference_id in candidate.reference_ids:
                    self.entity_ids_by_reference_id[reference_id].add(existing_id)
                return existing_id

        self.entity_candidates[candidate.id] = candidate
        for mention_id in candidate.mention_ids:
            self.entity_ids_by_mention_id[mention_id].add(candidate.id)
        for reference_id in candidate.reference_ids:
            self.entity_ids_by_reference_id[reference_id].add(candidate.id)
        for blocking_key in self._expanded_blocking_keys(candidate.blocking_key):
            self.entity_ids_by_blocking_key[blocking_key].add(candidate.id)
        if candidate.reuse_key is not None:
            self.entity_id_by_reuse_key[candidate.reuse_key] = candidate.id
        return candidate.id

    def add_fact_candidate(self, candidate: FactCandidate) -> FactCandidateId:
        self.fact_candidates[candidate.id] = candidate
        for entity_id in candidate.participating_entity_ids():
            self.fact_ids_by_entity_id[entity_id].add(candidate.id)
        return candidate.id

    def add_resolution_claim(self, claim: EntityResolutionClaim) -> ResolutionClaimId:
        self.resolution_claims[claim.id] = claim
        self.resolution_ids_by_entity_id[claim.left_entity_id].add(claim.id)
        self.resolution_ids_by_entity_id[claim.right_entity_id].add(claim.id)
        return claim.id

    def add_reference_resolution_claim(
        self,
        claim: ReferenceResolutionClaim,
    ) -> ResolutionClaimId:
        self.reference_resolution_claims[claim.id] = claim
        self.reference_resolution_ids_by_reference_id[claim.reference_id].add(claim.id)
        return claim.id

    def entity_ids_for_blocking_key(self, key: EntityBlockingKey) -> set[EntityCandidateId]:
        return set(self.entity_ids_by_blocking_key.get(key, set()))

    def entity_ids_for_mention(self, mention_id: MentionId) -> frozenset[EntityCandidateId]:
        return frozenset(self.entity_ids_by_mention_id.get(mention_id, set()))

    def entity_ids_for_reference(self, reference_id: MentionId) -> frozenset[EntityCandidateId]:
        return frozenset(self.entity_ids_by_reference_id.get(reference_id, set()))

    def references_for_sentence(self, sentence_id: SentenceId) -> tuple[ReferenceMention, ...]:
        return tuple(
            self.references[reference_id]
            for reference_id in self.reference_ids_by_sentence_id.get(sentence_id, set())
        )

    def sentence_id_for_offset(self, offset: int) -> SentenceId | None:
        for sentence in self.sentences.values():
            if sentence.span.start_char <= offset < sentence.span.end_char:
                return sentence.id
        return None

    def token_ids_for_span(
        self,
        *,
        sentence_id: SentenceId,
        span: EvidenceSpan,
    ) -> tuple[TokenId, ...]:
        sentence = self.sentences[sentence_id]
        return tuple(
            token_id
            for token_id in sentence.token_ids
            if self.tokens[token_id].span.start_char >= span.span.start_char
            and self.tokens[token_id].span.end_char <= span.span.end_char
        )

    def tokens_for_mention(self, mention_id: MentionId) -> tuple[Token, ...]:
        mention = self.mentions[mention_id]
        return tuple(self.tokens[token_id] for token_id in mention.token_ids)

    def candidate_ids_with_evidence_overlapping_span(
        self,
        span: EvidenceSpan,
    ) -> tuple[EntityCandidateId, ...]:
        matched: list[EntityCandidateId] = []
        for candidate in self.entity_candidates.values():
            for mention in self.candidate_mentions(candidate.id):
                evidence = self.evidence[mention.evidence_id]
                if evidence.span.contains(span.span) or span.span.contains(evidence.span):
                    matched.append(candidate.id)
                    break
        return tuple(dict.fromkeys(matched))

    def candidate_mentions(self, entity_id: EntityCandidateId) -> tuple[Mention, ...]:
        candidate = self.entity_candidates[entity_id]
        return tuple(self.mentions[mention_id] for mention_id in candidate.mention_ids)

    def candidate_references(self, entity_id: EntityCandidateId) -> tuple[ReferenceMention, ...]:
        candidate = self.entity_candidates[entity_id]
        return tuple(self.references[reference_id] for reference_id in candidate.reference_ids)

    def evidence_for_entity(self, entity_id: EntityCandidateId) -> tuple[EvidenceSpan, ...]:
        spans: list[EvidenceSpan] = []
        for mention in self.candidate_mentions(entity_id):
            spans.append(self.evidence[mention.evidence_id])
        for reference in self.candidate_references(entity_id):
            spans.append(self.evidence[reference.evidence_id])
        return tuple(spans)

    def facts_involving_entity(self, entity_id: EntityCandidateId) -> tuple[FactCandidate, ...]:
        return tuple(
            self.fact_candidates[fact_id]
            for fact_id in self.fact_ids_by_entity_id.get(entity_id, set())
        )

    def resolution_claims_for_entity(
        self,
        entity_id: EntityCandidateId,
    ) -> tuple[EntityResolutionClaim, ...]:
        return tuple(
            self.resolution_claims[claim_id]
            for claim_id in self.resolution_ids_by_entity_id.get(entity_id, set())
        )

    def reference_resolution_claims_for_reference(
        self,
        reference_id: MentionId,
    ) -> tuple[ReferenceResolutionClaim, ...]:
        return tuple(
            self.reference_resolution_claims[claim_id]
            for claim_id in self.reference_resolution_ids_by_reference_id.get(reference_id, set())
        )

    def candidates_by_kind(self, kind: EntityKind) -> tuple[EntityCandidate, ...]:
        return tuple(
            candidate for candidate in self.entity_candidates.values() if candidate.kind == kind
        )

    @staticmethod
    def _expanded_blocking_keys(
        key: EntityBlockingKey | None,
    ) -> tuple[EntityBlockingKey, ...]:
        if key is None:
            return ()
        return (key,)


def org_blocking_keys(key: OrganizationAcronymKey) -> tuple[EntityBlockingKey, ...]:
    return (key,)
