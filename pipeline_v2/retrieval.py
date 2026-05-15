from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import (
    EntityCandidate,
    EntityResolutionProposal,
)
from pipeline_v2.ids import EntityCandidateId
from pipeline_v2.nlp import Sentence
from pipeline_v2.store import ExtractionStore
from pipeline_v2.types import EntityKind, MentionKind, positive_signal


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
            if evidence_sentence.paragraph_index != anchor_sentence.paragraph_index:
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
        return ()

    def _person_proposals(
        self,
        entity: EntityCandidate,
    ) -> tuple[EntityResolutionProposal, ...]:
        surname_base = self._surname_base_for_surname_only_entity(entity)
        if surname_base is None:
            return ()

        proposals: list[EntityResolutionProposal] = []
        for candidate in self.store.candidates_by_kind(EntityKind.PERSON):
            candidate_id = candidate.id
            if candidate_id == entity.id:
                continue
            candidate_surname_base = candidate.person_surname_base()
            if candidate_surname_base != surname_base:
                continue
            distance = self._minimum_paragraph_distance(entity, candidate)
            if distance is None or distance > 1:
                continue
            evidence_ids = tuple(
                mention.evidence_id
                for mention in [
                    *self.store.candidate_mentions(entity.id),
                    *self.store.candidate_mentions(candidate.id),
                ]
            )
            proposals.append(
                EntityResolutionProposal(
                    left_entity_id=entity.id,
                    right_entity_id=candidate.id,
                    evidence_ids=evidence_ids,
                    retrieval_signals=(
                        positive_signal("same_surname_base"),
                        positive_signal(f"paragraph_distance:{distance}"),
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
