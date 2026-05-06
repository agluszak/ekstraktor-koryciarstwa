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
    EntityType,
    FactType,
    RelationshipType,
)
from pipeline.extraction_context import (
    ALL_ENTITY_TYPES,
    ExtractionContext,
    clusters_to_mention_views,
)
from pipeline.models import (
    ArticleDocument,
    ClusterMention,
    ClusterMentionView,
    Fact,
    SentenceFragment,
)
from pipeline.nlp_rules import TIE_WORDS
from pipeline.relation_signals import is_quote_speaker_risk
from pipeline.secondary_fact_helpers import (
    SecondaryFactScore,
    SecondaryFactScorer,
    build_secondary_fact,
)


class TieFactExtractor:
    def build(self, document: ArticleDocument, context: ExtractionContext) -> list[Fact]:
        facts: list[Fact] = []
        for sentence in document.sentences:
            sentence_views = context.mention_views_in_sentence(
                sentence.sentence_index, sentence.paragraph_index, ALL_ENTITY_TYPES
            )
            if not sentence_views:
                continue

            paragraph_views = context.mention_views_in_paragraph(
                sentence.paragraph_index, ALL_ENTITY_TYPES
            )
            previous_views = [
                v
                for v in clusters_to_mention_views(
                    context.clusters_in_sentence(sentence.sentence_index - 1, ALL_ENTITY_TYPES),
                    sentence.sentence_index - 1,
                    sentence.paragraph_index,
                )
                if v.paragraph_index == sentence.paragraph_index
            ]

            facts.extend(
                self._process_sentence(
                    document,
                    context,
                    sentence,
                    sentence_views,
                    paragraph_views,
                    previous_views,
                )
            )
        return facts

    def _process_sentence(
        self,
        document: ArticleDocument,
        context: ExtractionContext,
        sentence: SentenceFragment,
        sentence_views: list[ClusterMentionView],
        paragraph_views: list[ClusterMentionView],
        previous_views: list[ClusterMentionView],
    ) -> list[Fact]:
        parsed_words = document.parsed_sentences.get(sentence.sentence_index, [])
        trigger = self._tie_trigger(parsed_words, sentence.text.lower())
        if trigger is None:
            return self._complaint_context_ties(
                document, context, sentence, sentence_views, paragraph_views
            )
        facts: list[Fact] = []
        facts.extend(
            self._nearby_person_pairs(document, sentence, sentence_views, parsed_words, trigger)
        )
        if not facts:
            facts.extend(
                self._owner_context_ties(
                    document,
                    context,
                    sentence,
                    sentence_views,
                    paragraph_views,
                    parsed_words,
                    trigger,
                )
            )
        if not facts:
            facts.extend(
                self._complaint_context_ties(
                    document, context, sentence, sentence_views, paragraph_views
                )
            )
        return facts

    @staticmethod
    def _nearby_person_pairs(
        document: ArticleDocument,
        sentence: SentenceFragment,
        sentence_views: list[ClusterMentionView],
        parsed_words: list,
        trigger: str,
    ) -> list[Fact]:
        """Find exactly 2 nearby persons around a tie word and emit a tie fact."""
        lowered = sentence.text.lower()
        anchor = lowered.find(trigger)
        if anchor < 0:
            return []
        persons = [v for v in sentence_views if v.entity_type == EntityType.PERSON]
        nearby = [
            person
            for person in persons
            if abs(person.start_char - anchor) <= 80 or abs(person.end_char - anchor) <= 80
        ]
        if len(nearby) != 2 or nearby[0].entity_id == nearby[1].entity_id:
            return []
        source, target = nearby[0], nearby[1]
        confidence = 0.72
        score = SecondaryFactScorer.tie(parsed_words, source, target, trigger, confidence)
        return [
            build_secondary_fact(
                document=document,
                sentence=sentence,
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
    def _tie_trigger(parsed_words: list, lowered_text: str) -> str | None:
        lemma_tokens = {(word.lemma or word.text).casefold() for word in parsed_words}
        for trigger in TIE_WORDS:
            if " " not in trigger and trigger in lemma_tokens:
                return trigger
            if " " not in trigger and any(
                token.startswith(trigger[: max(5, len(trigger) - 2)]) for token in lemma_tokens
            ):
                return trigger
            pattern = rf"(?<!\w){re.escape(trigger)}(?!\w)"
            if re.search(pattern, lowered_text):
                return trigger
            if " " not in trigger and re.search(
                rf"(?<!\w){re.escape(trigger[: max(5, len(trigger) - 2)])}\w*",
                lowered_text,
            ):
                return trigger
        return None

    @staticmethod
    def _owner_context_ties(
        document: ArticleDocument,
        context: ExtractionContext,
        sentence: SentenceFragment,
        sentence_views: list[ClusterMentionView],
        paragraph_views: list[ClusterMentionView],
        parsed_words: list,
        trigger: str,
    ) -> list[Fact]:
        lowered = sentence.text.lower()
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
        persons = [v for v in sentence_views if v.entity_type == EntityType.PERSON]
        public_actors = [
            person
            for person in persons
            if person.start_char >= anchor
            and any(
                marker in lowered[max(0, person.start_char - 40) : person.end_char + 8]
                for marker in public_role_markers
            )
            and not is_quote_speaker_risk(parsed_words, person)
        ]
        if not public_actors:
            return []
        source = min(public_actors, key=lambda person: person.start_char)

        org_types = {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
        org_names = " ".join(
            v.normalized_name.lower() for v in sentence_views if v.entity_type in org_types
        )
        document_org_names = " ".join(
            entity.normalized_name.lower()
            for entity in document.entities
            if entity.entity_type in org_types
        )
        paragraph_persons = [v for v in paragraph_views if v.entity_type == EntityType.PERSON]
        owner_candidates = [
            person
            for person in paragraph_persons
            if person.entity_id != source.entity_id
            and person.canonical_name.split()
            and not _person_name_looks_like_company(person.canonical_name)
            and person.canonical_name.split()[-1].lower() in f"{org_names} {document_org_names}"
            and not is_quote_speaker_risk(parsed_words, person)
        ]
        owner_candidates.extend(
            _document_owner_person_candidates(
                document=document,
                context=context,
                sentence=sentence,
                source=source,
                lowered_text=lowered,
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
                document=document,
                sentence=sentence,
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

    def _complaint_context_ties(
        self,
        document: ArticleDocument,
        context: ExtractionContext,
        sentence: SentenceFragment,
        sentence_views: list[ClusterMentionView],
        paragraph_views: list[ClusterMentionView],
    ) -> list[Fact]:
        paragraph_text = self._paragraph_text(document, sentence)
        complaint_signal = detect_patronage_complaint(paragraph_text)
        if complaint_signal is None:
            return []

        parsed_words = document.parsed_sentences.get(sentence.sentence_index, [])
        paragraph_people = self._unique_people(
            [v for v in paragraph_views if v.entity_type == EntityType.PERSON]
        )
        if len(paragraph_people) < 2:
            return []

        source = self._complaint_source(
            document, sentence, sentence_views, paragraph_views, paragraph_text, parsed_words
        )
        if source is None:
            return []
        target_candidates = [
            candidate
            for candidate in paragraph_people
            if candidate.entity_id != source.entity_id
            and self._has_complaint_power_context(paragraph_text, candidate)
            and not self._looks_like_complaint_recipient(paragraph_text, candidate)
            and not is_quote_speaker_risk(parsed_words, candidate)
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
                document=document,
                sentence=sentence,
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
    def _paragraph_text(document: ArticleDocument, sentence: SentenceFragment) -> str:
        return " ".join(
            s.text.lower()
            for s in document.sentences
            if s.paragraph_index == sentence.paragraph_index
        )

    @staticmethod
    def _unique_people(views: list[ClusterMentionView]) -> list[ClusterMentionView]:
        unique: dict[str, ClusterMentionView] = {}
        for view in views:
            if view.entity_id is None:
                continue
            unique.setdefault(str(view.entity_id), view)
        return list(unique.values())

    def _complaint_source(
        self,
        document: ArticleDocument,
        sentence: SentenceFragment,
        sentence_views: list[ClusterMentionView],
        paragraph_views: list[ClusterMentionView],
        paragraph_text: str,
        parsed_words: list,
    ) -> ClusterMentionView | None:
        sentence_persons = self._unique_people(
            [
                v
                for v in sentence_views
                if v.entity_type == EntityType.PERSON and not is_quote_speaker_risk(parsed_words, v)
            ]
        )
        if not sentence_persons:
            sentence_persons = self._unique_people(
                [
                    v
                    for v in paragraph_views
                    if v.entity_type == EntityType.PERSON
                    and not is_quote_speaker_risk(parsed_words, v)
                ]
            )
        if not sentence_persons:
            return None
        speaker_candidates = [
            v
            for v in sentence_persons
            if self._has_speaker_context(paragraph_text, v)
            and not self._looks_like_complaint_recipient(paragraph_text, v)
        ]
        if speaker_candidates:
            return max(
                speaker_candidates,
                key=lambda v: (
                    self._has_whistleblower_context(paragraph_text, v),
                    -v.start_char,
                ),
            )
        return min(
            (
                v
                for v in sentence_persons
                if not self._has_complaint_power_context(paragraph_text, v)
                and not self._looks_like_complaint_recipient(paragraph_text, v)
            ),
            key=lambda v: v.start_char,
            default=None,
        )

    @staticmethod
    def _has_speaker_context(paragraph_text: str, view: ClusterMentionView) -> bool:
        window = _candidate_context_window(paragraph_text, view)
        return has_speaker_markers(window)

    @staticmethod
    def _has_complaint_power_context(paragraph_text: str, view: ClusterMentionView) -> bool:
        window = _candidate_context_window(paragraph_text, view)
        return has_power_holder_markers(window)

    @staticmethod
    def _has_whistleblower_context(paragraph_text: str, view: ClusterMentionView) -> bool:
        window = _candidate_context_window(paragraph_text, view)
        return has_whistleblower_markers(window)

    @staticmethod
    def _looks_like_complaint_recipient(paragraph_text: str, view: ClusterMentionView) -> bool:
        window = _candidate_context_window(paragraph_text, view)
        return has_complaint_recipient_markers(window)


def _candidate_context_window(paragraph_text: str, view: ClusterMentionView) -> str:
    names = [
        view.canonical_name.lower(),
        view.normalized_name.lower(),
    ]
    if view.canonical_name.split():
        names.append(view.canonical_name.split()[0].lower())
    if view.canonical_name.split():
        names.append(view.canonical_name.split()[-1].lower())
    for name in names:
        anchor = paragraph_text.find(name)
        if anchor >= 0:
            return paragraph_text[max(0, anchor - 64) : anchor + len(name) + 64]
    return paragraph_text[:128]


def _document_owner_person_candidates(
    *,
    document: ArticleDocument,
    context: ExtractionContext,
    sentence: SentenceFragment,
    source: ClusterMentionView,
    lowered_text: str,
    document_org_names: str,
) -> list[ClusterMentionView]:
    if not any(marker in lowered_text for marker in ("firmą prowadzon", "firma prowadzon")):
        return []
    views: list[ClusterMentionView] = []
    for entity in document.entities:
        if entity.entity_type != EntityType.PERSON or entity.entity_id == source.entity_id:
            continue
        if _person_name_looks_like_company(entity.canonical_name):
            continue
        tokens = entity.canonical_name.split()
        if len(tokens) < 2 or tokens[-1].lower() not in document_org_names:
            continue
        cluster = context.cluster_by_entity_id(entity.entity_id)
        if cluster is None:
            continue
        # Synthetic mention with zero offsets: positional fields are not used here
        # (only canonical_name / entity_id are needed for tie fact construction).
        synthetic_mention = ClusterMention(
            text=entity.canonical_name,
            entity_type=EntityType.PERSON,
            sentence_index=sentence.sentence_index,
            paragraph_index=sentence.paragraph_index,
            start_char=0,
            end_char=0,
            entity_id=entity.entity_id,
        )
        views.append(ClusterMentionView(cluster=cluster, mention=synthetic_mention))
    return views


def _person_name_looks_like_company(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in ("consulting", "group", "spół", "firma"))
