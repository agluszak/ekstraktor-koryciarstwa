from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import (
    EntityCandidate,
    EntityResolutionProposal,
)
from pipeline_v2.ids import EntityCandidateId
from pipeline_v2.nlp import Sentence
from pipeline_v2.store import ExtractionStore
from pipeline_v2.types import (
    DescriptorPersonCandidateSignal,
    EntityKind,
    FullNameReuseMatchSignal,
    GroundingKind,
    LemmaMatchSignal,
    MentionKind,
    NearbyPersonCandidateSignal,
    Signal,
    SurnameBaseMatchSignal,
)


@dataclass(frozen=True, slots=True)
class SentenceEntity:
    id: EntityCandidateId
    kind: EntityKind
    start_char: int
    end_char: int


class SentenceEntityRetriever:
    def __init__(self, store: ExtractionStore) -> None:
        self.store = store

    def entities_for_sentence(self, sentence: Sentence) -> tuple[SentenceEntity, ...]:
        entities: list[SentenceEntity] = []
        for candidate in self.store.entity_candidates.values():
            entity = self._sentence_entity(sentence, candidate)
            if entity is not None:
                entities.append(entity)
        return tuple(sorted(entities, key=lambda entity: entity.start_char))

    def entities_for_sentence_window(
        self,
        sentence: Sentence,
        *,
        before: int,
        after: int,
    ) -> tuple[SentenceEntity, ...]:
        entities: list[SentenceEntity] = []
        min_index = sentence.sentence_index - before
        max_index = sentence.sentence_index + after
        for candidate in self.store.entity_candidates.values():
            entity = self._sentence_window_entity(
                sentence,
                candidate,
                min_index=min_index,
                max_index=max_index,
            )
            if entity is not None:
                entities.append(entity)
        return tuple(sorted(entities, key=lambda entity: entity.start_char))

    def _sentence_entity(
        self,
        sentence: Sentence,
        candidate: EntityCandidate,
    ) -> SentenceEntity | None:
        spans: list[tuple[int, int]] = []
        for evidence in self.store.evidence_for_entity(candidate.id):
            if evidence.sentence_id == sentence.id:
                spans.append((evidence.span.start_char, evidence.span.end_char))
        if not spans:
            return None
        return SentenceEntity(
            id=candidate.id,
            kind=candidate.kind,
            start_char=min(start for start, _end in spans),
            end_char=max(end for _start, end in spans),
        )

    def _sentence_window_entity(
        self,
        anchor_sentence: Sentence,
        candidate: EntityCandidate,
        *,
        min_index: int,
        max_index: int,
    ) -> SentenceEntity | None:
        spans: list[tuple[int, int]] = []
        for evidence in self.store.evidence_for_entity(candidate.id):
            if evidence.sentence_id is None:
                continue
            evidence_sentence = self.store.sentences[evidence.sentence_id]
            idx_dist = abs(evidence_sentence.sentence_index - anchor_sentence.sentence_index)
            is_same_para = evidence_sentence.paragraph_index == anchor_sentence.paragraph_index
            # Allow adjacent sentences (distance ≤ 1) to cross paragraph boundaries —
            # news articles often break paragraphs mid-thought, so the subject may
            # appear at end of paragraph N-1 and the fact in paragraph N.
            if not (is_same_para or idx_dist <= 1):
                continue
            if min_index <= evidence_sentence.sentence_index <= max_index:
                spans.append((evidence.span.start_char, evidence.span.end_char))
        if not spans:
            return None
        return SentenceEntity(
            id=candidate.id,
            kind=candidate.kind,
            start_char=min(start for start, _end in spans),
            end_char=max(end for _start, end in spans),
        )


class EntityCandidateRetriever:
    def __init__(self, store: ExtractionStore) -> None:
        self.store = store

    def proposals_for_entity(self, entity: EntityCandidate) -> tuple[EntityResolutionProposal, ...]:
        if entity.kind == EntityKind.PERSON:
            return self._person_proposals(entity)
        if entity.kind == EntityKind.ORGANIZATION:
            return self._organization_proposals(entity)
        if entity.kind == EntityKind.ROLE:
            return self._role_proposals(entity)
        return ()

    def _person_proposals(
        self,
        entity: EntityCandidate,
    ) -> tuple[EntityResolutionProposal, ...]:
        reuse_key = entity.reuse_key
        surname_base = entity.person_surname_base() or self._surname_base_for_surname_only_entity(
            entity
        )

        proposals: list[EntityResolutionProposal] = []
        for candidate in self.store.candidates_by_kind(EntityKind.PERSON):
            candidate_id = candidate.id
            if candidate_id == entity.id:
                continue

            # If both have different full names, do not propose merging them!
            if (
                reuse_key is not None
                and candidate.reuse_key is not None
                and reuse_key.given_name_lemma != candidate.reuse_key.given_name_lemma
            ):
                continue

            # 1. Full name match via reuse_key
            if reuse_key is not None and candidate.reuse_key == reuse_key:
                proposals.append(
                    self._build_proposal(entity, candidate, FullNameReuseMatchSignal())
                )
                continue

            # 2. Surname base match
            candidate_surname_base = (
                candidate.person_surname_base()
                or self._surname_base_for_surname_only_entity(candidate)
            )
            if surname_base is not None and candidate_surname_base == surname_base:
                distance = self._minimum_paragraph_distance(entity, candidate)
                if distance is not None and distance <= 3:
                    proposals.append(
                        self._build_proposal(
                            entity, candidate, SurnameBaseMatchSignal(distance=distance)
                        )
                    )
                continue

        proposals.extend(self._descriptor_person_proposals(entity))
        return tuple(proposals)

    def _organization_proposals(
        self,
        entity: EntityCandidate,
    ) -> tuple[EntityResolutionProposal, ...]:
        # TODO: Implement organization acronym matching
        return ()

    def _role_proposals(
        self,
        entity: EntityCandidate,
    ) -> tuple[EntityResolutionProposal, ...]:
        role_lemma = self._role_head_lemma(entity)
        if role_lemma is None:
            return ()
        proposals: list[EntityResolutionProposal] = []
        for candidate in self.store.candidates_by_kind(EntityKind.ROLE):
            if candidate.id == entity.id:
                continue
            candidate_lemma = self._role_head_lemma(candidate)
            if candidate_lemma != role_lemma:
                continue
            distance = self._minimum_paragraph_distance(entity, candidate)
            if distance is None or distance > 3:
                continue
            proposals.append(
                self._build_proposal(
                    entity,
                    candidate,
                    LemmaMatchSignal(lemma=role_lemma),
                )
            )
        return tuple(proposals)

    def _build_proposal(
        self,
        left: EntityCandidate,
        right: EntityCandidate,
        *signals: Signal,
    ) -> EntityResolutionProposal:
        evidence_ids = tuple(
            mention.evidence_id
            for mention in [
                *self.store.candidate_mentions(left.id),
                *self.store.candidate_mentions(right.id),
            ]
        )
        return EntityResolutionProposal(
            left_entity_id=left.id,
            right_entity_id=right.id,
            evidence_ids=evidence_ids,
            retrieval_signals=signals,
        )

    def _descriptor_person_proposals(
        self,
        entity: EntityCandidate,
    ) -> tuple[EntityResolutionProposal, ...]:
        descriptor_lemma = self._descriptor_person_lemma(entity)
        if descriptor_lemma is None:
            return ()
        proposals: list[EntityResolutionProposal] = []
        for candidate in self.store.candidates_by_kind(EntityKind.PERSON):
            if candidate.id == entity.id or self._descriptor_person_lemma(candidate) is not None:
                continue
            if candidate.grounding is not GroundingKind.OBSERVED:
                continue
            sentence_distance = self._minimum_sentence_distance(entity, candidate)
            if sentence_distance is None or sentence_distance > 1:
                continue
            paragraph_distance = self._minimum_paragraph_distance(entity, candidate)
            if paragraph_distance is not None and paragraph_distance > 1:
                continue
            proposals.append(
                self._build_proposal(
                    entity,
                    candidate,
                    NearbyPersonCandidateSignal(),
                    DescriptorPersonCandidateSignal(
                        descriptor_lemma=descriptor_lemma,
                        sentence_distance=sentence_distance,
                    ),
                )
            )
        return tuple(proposals)

    def _surname_base_for_surname_only_entity(self, entity: EntityCandidate) -> str | None:
        for mention in self.store.candidate_mentions(entity.id):
            if mention.kind != MentionKind.SURNAME_ONLY:
                continue
            if mention.head_lemma is not None:
                return mention.head_lemma.casefold()
        return None

    def _minimum_paragraph_distance(
        self,
        left: EntityCandidate,
        right: EntityCandidate,
    ) -> int | None:
        left_paragraphs = [
            self.store.evidence[mention.evidence_id].paragraph_index
            for mention in self.store.candidate_mentions(left.id)
        ]
        right_paragraphs = [
            self.store.evidence[mention.evidence_id].paragraph_index
            for mention in self.store.candidate_mentions(right.id)
        ]
        distances = [
            abs(left_paragraph - right_paragraph)
            for left_paragraph in left_paragraphs
            for right_paragraph in right_paragraphs
            if left_paragraph is not None and right_paragraph is not None
        ]
        return min(distances) if distances else None

    def _descriptor_person_lemma(self, entity: EntityCandidate) -> str | None:
        if entity.kind is not EntityKind.PERSON:
            return None
        for mention in self.store.candidate_mentions(entity.id):
            if mention.kind is not MentionKind.DESCRIPTOR_NOUN_PHRASE:
                continue
            if mention.head_lemma is not None:
                return mention.head_lemma.casefold()
            return mention.text.casefold()
        if entity.grounding is GroundingKind.INFERRED and entity.canonical_hint is not None:
            return entity.canonical_hint.casefold()
        return None

    def _role_head_lemma(self, entity: EntityCandidate) -> str | None:
        if entity.kind is not EntityKind.ROLE:
            return None
        for mention in self.store.candidate_mentions(entity.id):
            if mention.head_lemma is not None:
                return mention.head_lemma.casefold()
            return mention.text.casefold()
        if entity.canonical_hint is not None:
            return entity.canonical_hint.casefold()
        return None

    def _minimum_sentence_distance(
        self,
        left: EntityCandidate,
        right: EntityCandidate,
    ) -> int | None:
        left_sentence_ids = {
            evidence.sentence_id for evidence in self.store.evidence_for_entity(left.id)
        } - {None}
        right_sentence_ids = {
            evidence.sentence_id for evidence in self.store.evidence_for_entity(right.id)
        } - {None}
        if not left_sentence_ids or not right_sentence_ids:
            return None
        if left_sentence_ids & right_sentence_ids:
            return 0
        left_indexes = [
            self.store.sentences[sentence_id].sentence_index
            for sentence_id in left_sentence_ids
            if sentence_id in self.store.sentences
        ]
        right_indexes = [
            self.store.sentences[sentence_id].sentence_index
            for sentence_id in right_sentence_ids
            if sentence_id in self.store.sentences
        ]
        if not left_indexes or not right_indexes:
            return None
        return min(
            abs(left_index - right_index)
            for left_index in left_indexes
            for right_index in right_indexes
        )
