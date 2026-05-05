from __future__ import annotations

import re

from pipeline.complaint_classifier import (
    detect_patronage_complaint,
    has_complaint_recipient_markers,
    has_power_holder_markers,
    has_speaker_markers,
    has_whistleblower_markers,
)
from pipeline.domain_types import (
    CandidateID,
    CandidateType,
    EntityType,
    FactType,
    RelationshipType,
)
from pipeline.extraction_context import (
    ExtractionContext,
    SentenceContext,
    clusters_to_sentence_candidates,
)
from pipeline.models import ArticleDocument, EntityCandidate, Fact
from pipeline.nlp_rules import TIE_WORDS
from pipeline.secondary_fact_helpers import (
    SecondaryFactScore,
    SecondaryFactScorer,
    _is_quote_speaker_risk,
    build_secondary_fact,
)
from pipeline.utils import stable_id

_ALL_TYPES = {
    EntityType.PERSON,
    EntityType.POLITICAL_PARTY,
    EntityType.POSITION,
    EntityType.ORGANIZATION,
    EntityType.PUBLIC_INSTITUTION,
    EntityType.LOCATION,
}


class TieFactExtractor:
    def build(self, document: ArticleDocument, context: ExtractionContext) -> list[Fact]:
        facts: list[Fact] = []
        for sentence in document.sentences:
            sentence_clusters = context.clusters_in_sentence(sentence.sentence_index, _ALL_TYPES)
            sentence_candidates = clusters_to_sentence_candidates(
                sentence_clusters, sentence.sentence_index, sentence.paragraph_index
            )
            if not sentence_candidates:
                continue

            paragraph_clusters = sum(
                (
                    context.clusters_in_sentence(s.sentence_index, _ALL_TYPES)
                    for s in document.sentences
                    if s.paragraph_index == sentence.paragraph_index
                ),
                [],
            )
            seen: set[str] = set()
            unique_paragraph = []
            for c in paragraph_clusters:
                key = str(c.cluster_id)
                if key not in seen:
                    seen.add(key)
                    unique_paragraph.append(c)

            prev_sentence_clusters = context.clusters_in_sentence(
                sentence.sentence_index - 1, _ALL_TYPES
            )
            previous_candidates = [
                c
                for c in clusters_to_sentence_candidates(
                    prev_sentence_clusters, sentence.sentence_index - 1, sentence.paragraph_index
                )
                if c.paragraph_index == sentence.paragraph_index
            ]

            sentence_context = SentenceContext(
                document=document,
                sentence=sentence,
                parsed_words=document.parsed_sentences.get(sentence.sentence_index, []),
                candidates=sentence_candidates,
                paragraph_candidates=clusters_to_sentence_candidates(
                    unique_paragraph, sentence.sentence_index, sentence.paragraph_index
                ),
                previous_candidates=previous_candidates,
            )
            facts.extend(self._process_sentence(sentence_context))
        return facts

    def _process_sentence(self, context: SentenceContext) -> list[Fact]:
        trigger = self._tie_trigger(context)
        if trigger is None:
            return self._complaint_context_ties(context)
        facts: list[Fact] = []
        facts.extend(self._nearby_person_pairs(context, trigger))
        if not facts:
            facts.extend(self._owner_context_ties(context, trigger))
        if not facts:
            facts.extend(self._complaint_context_ties(context))
        return facts

    def _nearby_person_pairs(self, context: SentenceContext, trigger: str) -> list[Fact]:
        """Find exactly 2 nearby persons around a tie word and emit a tie fact."""
        lowered = context.lowered_text
        anchor = lowered.find(trigger)
        if anchor < 0:
            return []
        persons = context.persons
        nearby = [
            person
            for person in persons
            if abs(person.start_char - anchor) <= 80 or abs(person.end_char - anchor) <= 80
        ]
        if len(nearby) != 2 or nearby[0].entity_id == nearby[1].entity_id:
            return []
        source, target = nearby[0], nearby[1]
        confidence = 0.72
        score = SecondaryFactScorer.tie(context, source, target, trigger, confidence)
        return [
            build_secondary_fact(
                document=context.document,
                sentence_context=context,
                fact_type=FactType.PERSONAL_OR_POLITICAL_TIE,
                subject=source,
                object_candidate=target,
                value_text=TIE_WORDS[trigger].value,
                value_normalized=TIE_WORDS[trigger].value,
                confidence=score.confidence,
                score=score,
                source_extractor="tie",
                relationship_type=TIE_WORDS[trigger],
            )
        ]

    @staticmethod
    def _tie_trigger(context: SentenceContext) -> str | None:
        lemma_tokens = {(word.lemma or word.text).casefold() for word in context.parsed_words}
        text = context.lowered_text
        for trigger in TIE_WORDS:
            if " " not in trigger and trigger in lemma_tokens:
                return trigger
            if " " not in trigger and any(
                token.startswith(trigger[: max(5, len(trigger) - 2)]) for token in lemma_tokens
            ):
                return trigger
            pattern = rf"(?<!\w){re.escape(trigger)}(?!\w)"
            if re.search(pattern, text):
                return trigger
            if " " not in trigger and re.search(
                rf"(?<!\w){re.escape(trigger[: max(5, len(trigger) - 2)])}\w*",
                text,
            ):
                return trigger
        return None

    @staticmethod
    def _owner_context_ties(context: SentenceContext, trigger: str) -> list[Fact]:
        lowered = context.lowered_text
        anchor = lowered.find(trigger)
        if anchor < 0:
            anchor = min(
                (
                    lowered.find(marker)
                    for marker in ("współpracownik", "koleg", "znajom", "przyjaciel")
                    if lowered.find(marker) >= 0
                ),
                default=-1,
            )
        if anchor < 0:
            return []
        public_role_markers = ("prezydent", "burmistrz", "wójt", "minister", "poseł", "radny")
        public_actors = [
            person
            for person in context.persons
            if person.start_char >= anchor
            and any(
                marker in lowered[max(0, person.start_char - 40) : person.end_char + 8]
                for marker in public_role_markers
            )
            and not _is_quote_speaker_risk(context, person)
        ]
        if not public_actors:
            return []
        source = min(public_actors, key=lambda person: person.start_char)

        org_names = " ".join(org.normalized_name.lower() for org in context.organizations)
        document_org_names = " ".join(
            entity.normalized_name.lower()
            for entity in context.document.entities
            if entity.entity_type in {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
        )
        owner_candidates = [
            person
            for person in context.paragraph_persons
            if person.entity_id != source.entity_id
            and person.canonical_name.split()
            and not _person_name_looks_like_company(person.canonical_name)
            and person.canonical_name.split()[-1].lower() in f"{org_names} {document_org_names}"
            and not _is_quote_speaker_risk(context, person)
        ]
        owner_candidates.extend(
            _document_owner_person_candidates(
                context,
                source=source,
                document_org_names=document_org_names,
            )
        )
        if not owner_candidates:
            return []
        target = min(owner_candidates, key=lambda person: abs(person.start_char - anchor))
        score = SecondaryFactScore(
            confidence=0.78,
            extraction_signal="dependency_edge",
            evidence_scope="same_paragraph",
            reason=f"tie_trigger:{trigger}:owner_context",
        )
        return [
            build_secondary_fact(
                document=context.document,
                sentence_context=context,
                fact_type=FactType.PERSONAL_OR_POLITICAL_TIE,
                subject=source,
                object_candidate=target,
                value_text=TIE_WORDS[trigger].value,
                value_normalized=TIE_WORDS[trigger].value,
                confidence=score.confidence,
                score=score,
                source_extractor="tie",
                relationship_type=TIE_WORDS[trigger],
            )
        ]

    def _complaint_context_ties(self, context: SentenceContext) -> list[Fact]:
        paragraph_text = self._paragraph_text(context)
        complaint_signal = detect_patronage_complaint(paragraph_text)
        if complaint_signal is None:
            return []

        paragraph_people = self._unique_people(context.paragraph_persons)
        if len(paragraph_people) < 2:
            return []

        source = self._complaint_source(context)
        if source is None:
            return []
        target_candidates = [
            candidate
            for candidate in paragraph_people
            if candidate.entity_id != source.entity_id
            and self._has_complaint_power_context(context, candidate)
            and not self._looks_like_complaint_recipient(context, candidate)
            and not _is_quote_speaker_risk(context, candidate)
        ]
        if not target_candidates:
            return []
        anchor = paragraph_text.find("kolesi")
        if anchor < 0:
            anchor = min(
                (paragraph_text.find(marker) for marker in complaint_signal.patronage_markers),
                default=-1,
            )
        if anchor < 0:
            anchor = source.start_char
        target = min(
            target_candidates,
            key=lambda candidate: (abs(candidate.start_char - anchor), candidate.start_char),
        )
        score = SecondaryFactScore(
            confidence=0.76,
            extraction_signal="same_paragraph",
            evidence_scope="same_paragraph",
            reason="complaint_patronage_context",
        )
        return [
            build_secondary_fact(
                document=context.document,
                sentence_context=context,
                fact_type=FactType.PERSONAL_OR_POLITICAL_TIE,
                subject=source,
                object_candidate=target,
                value_text=RelationshipType.ASSOCIATE.value,
                value_normalized=RelationshipType.ASSOCIATE.value,
                confidence=score.confidence,
                score=score,
                source_extractor="tie",
                relationship_type=RelationshipType.ASSOCIATE,
            )
        ]

    @staticmethod
    def _paragraph_text(context: SentenceContext) -> str:
        return " ".join(
            sentence.text.lower()
            for sentence in context.document.sentences
            if sentence.paragraph_index == context.sentence.paragraph_index
        )

    @staticmethod
    def _unique_people(candidates: list[EntityCandidate]) -> list[EntityCandidate]:
        unique: dict[str, EntityCandidate] = {}
        for candidate in candidates:
            if candidate.entity_id is None:
                continue
            unique.setdefault(str(candidate.entity_id), candidate)
        return list(unique.values())

    def _complaint_source(self, context: SentenceContext) -> EntityCandidate | None:
        sentence_people = [
            candidate
            for candidate in self._unique_people(context.persons)
            if not _is_quote_speaker_risk(context, candidate)
        ]
        if not sentence_people:
            sentence_people = [
                candidate
                for candidate in self._unique_people(context.paragraph_persons)
                if not _is_quote_speaker_risk(context, candidate)
            ]
        if not sentence_people:
            return None
        speaker_candidates = [
            candidate
            for candidate in sentence_people
            if self._has_speaker_context(context, candidate)
            and not self._looks_like_complaint_recipient(context, candidate)
        ]
        if speaker_candidates:
            return max(
                speaker_candidates,
                key=lambda candidate: (
                    self._has_whistleblower_context(context, candidate),
                    -candidate.start_char,
                ),
            )
        return min(
            (
                candidate
                for candidate in sentence_people
                if not self._has_complaint_power_context(context, candidate)
                and not self._looks_like_complaint_recipient(context, candidate)
            ),
            key=lambda candidate: candidate.start_char,
            default=None,
        )

    def _has_speaker_context(self, context: SentenceContext, candidate: EntityCandidate) -> bool:
        window = self._candidate_context_window(context, candidate)
        return has_speaker_markers(window)

    def _has_complaint_power_context(
        self,
        context: SentenceContext,
        candidate: EntityCandidate,
    ) -> bool:
        window = self._candidate_context_window(context, candidate)
        return has_power_holder_markers(window)

    def _has_whistleblower_context(
        self,
        context: SentenceContext,
        candidate: EntityCandidate,
    ) -> bool:
        window = self._candidate_context_window(context, candidate)
        return has_whistleblower_markers(window)

    def _looks_like_complaint_recipient(
        self,
        context: SentenceContext,
        candidate: EntityCandidate,
    ) -> bool:
        window = self._candidate_context_window(context, candidate)
        return has_complaint_recipient_markers(window)

    @staticmethod
    def _candidate_context_window(context: SentenceContext, candidate: EntityCandidate) -> str:
        paragraph_text = TieFactExtractor._paragraph_text(context)
        names = [
            candidate.canonical_name.lower(),
            candidate.normalized_name.lower(),
        ]
        if candidate.canonical_name.split():
            names.append(candidate.canonical_name.split()[0].lower())
        if candidate.canonical_name.split():
            names.append(candidate.canonical_name.split()[-1].lower())
        for name in names:
            anchor = paragraph_text.find(name)
            if anchor >= 0:
                return paragraph_text[max(0, anchor - 64) : anchor + len(name) + 64]
        return paragraph_text[:128]


def _document_owner_person_candidates(
    context: SentenceContext,
    *,
    source: EntityCandidate,
    document_org_names: str,
) -> list[EntityCandidate]:
    candidates: list[EntityCandidate] = []
    if not any(marker in context.lowered_text for marker in ("firmą prowadzon", "firma prowadzon")):
        return candidates
    for entity in context.document.entities:
        if entity.entity_type != EntityType.PERSON or entity.entity_id == source.entity_id:
            continue
        if _person_name_looks_like_company(entity.canonical_name):
            continue
        tokens = entity.canonical_name.split()
        if len(tokens) < 2 or tokens[-1].lower() not in document_org_names:
            continue
        candidates.append(
            EntityCandidate(
                candidate_id=CandidateID(
                    stable_id(
                        "candidate",
                        context.document.document_id,
                        entity.entity_id,
                        str(context.sentence.sentence_index),
                        "owner-context",
                    )
                ),
                entity_id=entity.entity_id,
                candidate_type=CandidateType.PERSON,
                canonical_name=entity.canonical_name,
                normalized_name=entity.normalized_name,
                sentence_index=context.sentence.sentence_index,
                paragraph_index=context.sentence.paragraph_index,
                start_char=0,
                end_char=0,
                source="document_owner_context",
            )
        )
    return candidates


def _person_name_looks_like_company(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in ("consulting", "group", "spół", "firma"))
