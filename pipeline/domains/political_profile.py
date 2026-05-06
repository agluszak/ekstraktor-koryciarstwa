from __future__ import annotations

from pipeline.attribution import (
    resolve_candidacy_score,
    resolve_party_attributions,
    resolve_political_role_attributions,
)
from pipeline.domain_types import (
    EntityID,
    EntityType,
    FactID,
    FactType,
    TimeScope,
)
from pipeline.extraction_context import (
    ExtractionContext,
    clusters_to_mention_views,
)
from pipeline.models import (
    ArticleDocument,
    ClusterMentionView,
    EvidenceSpan,
    Fact,
    ParsedWord,
    SentenceFragment,
)
from pipeline.nlp_rules import (
    APPOINTMENT_TRIGGER_LEMMAS,
    APPOINTMENT_TRIGGER_TEXTS,
    DISMISSAL_TRIGGER_LEMMAS,
    DISMISSAL_TRIGGER_TEXTS,
    PARTY_PROFILE_CONTEXT_LEMMAS,
)
from pipeline.secondary_fact_helpers import (
    _has_signal,
    build_secondary_fact,
)
from pipeline.utils import stable_id

OMITTED_SUBJECT_PARTY_LEMMAS = frozenset(
    {"należeć", "członek", "członkini", "kandydować", "startować"}
)
OMITTED_SUBJECT_PARTY_MARKERS = (
    "należy do",
    "członk",
    "kandyd",
    "startował",
    "startowała",
)

_PERSON_TYPES = {EntityType.PERSON}
_PARTY_TYPES = {EntityType.POLITICAL_PARTY}
_POSITION_TYPES = {EntityType.POSITION}
_ORG_TYPES = {EntityType.ORGANIZATION, EntityType.PUBLIC_INSTITUTION}
_LOCATION_TYPES = {EntityType.LOCATION}
_ALL_TYPES = {
    EntityType.PERSON,
    EntityType.POLITICAL_PARTY,
    EntityType.POSITION,
    EntityType.ORGANIZATION,
    EntityType.PUBLIC_INSTITUTION,
    EntityType.LOCATION,
}


class PoliticalProfileFactExtractor:
    def build(self, document: ArticleDocument, context: ExtractionContext) -> list[Fact]:
        facts: list[Fact] = []
        for sentence in document.sentences:
            sentence_views = context.mention_views_in_sentence(
                sentence.sentence_index, sentence.paragraph_index, _ALL_TYPES
            )
            if not any(v.entity_type == EntityType.PERSON for v in sentence_views):
                continue
            facts.extend(self._extract_sentence(document, context, sentence))
        return facts

    def _extract_sentence(
        self,
        document: ArticleDocument,
        context: ExtractionContext,
        sentence: SentenceFragment,
    ) -> list[Fact]:
        facts: list[Fact] = []
        parsed_words = document.parsed_sentences.get(sentence.sentence_index, [])
        lowered_text = sentence.text.lower()
        governance_signal = _has_signal(
            parsed_words,
            lowered_text,
            APPOINTMENT_TRIGGER_LEMMAS | DISMISSAL_TRIGGER_LEMMAS,
            APPOINTMENT_TRIGGER_TEXTS | DISMISSAL_TRIGGER_TEXTS,
        )
        persons = [
            v
            for v in context.mention_views_in_sentence(
                sentence.sentence_index, sentence.paragraph_index, {EntityType.PERSON}
            )
            if not v.is_proxy_person
        ]
        for person in persons:
            for attribution in resolve_party_attributions(
                context,
                sentence,
                person,
                governance_signal=governance_signal,
            ):
                time_scope_val = _sentence_time_scope(document, sentence, parsed_words)
                fact_type = (
                    FactType.FORMER_PARTY_MEMBERSHIP
                    if time_scope_val == TimeScope.FORMER
                    else FactType.PARTY_MEMBERSHIP
                )
                facts.append(
                    build_secondary_fact(
                        document=document,
                        sentence=sentence,
                        fact_type=fact_type,
                        subject=attribution.person,
                        object_candidate=attribution.party,
                        value_text=attribution.party.canonical_name,
                        value_normalized=attribution.party.normalized_name,
                        confidence=attribution.score.confidence,
                        score=attribution.score,
                        source_extractor="political_profile",
                        party=attribution.party.canonical_name,
                    )
                )

            for attribution in resolve_political_role_attributions(
                context,
                sentence,
                person,
                governance_signal=governance_signal,
            ):
                facts.append(
                    build_secondary_fact(
                        document=document,
                        sentence=sentence,
                        fact_type=FactType.POLITICAL_OFFICE,
                        subject=attribution.person,
                        object_candidate=attribution.role,
                        value_text=attribution.role.canonical_name,
                        value_normalized=attribution.role.normalized_name,
                        confidence=attribution.score.confidence,
                        score=attribution.score,
                        source_extractor="political_profile",
                        office_type=attribution.role.canonical_name,
                    )
                )

            candidacy_score = resolve_candidacy_score(context, sentence, person)
            if candidacy_score is not None:
                facts.append(
                    build_secondary_fact(
                        document=document,
                        sentence=sentence,
                        fact_type=FactType.ELECTION_CANDIDACY,
                        subject=person,
                        object_candidate=None,
                        value_text=None,
                        value_normalized=None,
                        confidence=candidacy_score.confidence,
                        score=candidacy_score,
                        source_extractor="political_profile",
                        candidacy_scope="mentioned",
                    )
                )
        return facts


class CrossSentencePartyFactBuilder:
    def build(self, document: ArticleDocument, context: ExtractionContext) -> list[Fact]:
        facts: list[Fact] = []
        for sentence in document.sentences:
            sentence_views = context.mention_views_in_sentence(
                sentence.sentence_index, sentence.paragraph_index, _ALL_TYPES
            )
            parties = [
                v
                for v in sentence_views
                if v.entity_type == EntityType.POLITICAL_PARTY and v.entity_id is not None
            ]
            if not parties:
                continue
            lowered = sentence.text.lower()
            parsed_words = document.parsed_sentences.get(sentence.sentence_index, [])
            if parsed_words:
                has_party_context = any(
                    word.lemma.casefold() in PARTY_PROFILE_CONTEXT_LEMMAS for word in parsed_words
                )
            else:
                has_party_context = any(
                    marker in lowered
                    for marker in ("działacz", "polityk", "radn", "lider", "członk")
                )
            has_omitted_subject_trigger = self._has_omitted_subject_party_trigger(
                parsed_words, lowered
            )
            if not has_party_context and not has_omitted_subject_trigger:
                continue
            if any(v.entity_type == EntityType.PERSON for v in sentence_views):
                continue
            previous_persons = [
                v
                for previous_sentence in document.sentences
                if previous_sentence.paragraph_index == sentence.paragraph_index
                and previous_sentence.sentence_index < sentence.sentence_index
                for v in clusters_to_mention_views(
                    context.clusters_in_sentence(previous_sentence.sentence_index, _ALL_TYPES),
                    previous_sentence.sentence_index,
                    previous_sentence.paragraph_index,
                )
                if v.entity_type == EntityType.PERSON and v.entity_id is not None
            ]
            unique_previous_people: dict[EntityID, ClusterMentionView] = {}
            for person_view in previous_persons:
                assert person_view.entity_id is not None
                unique_previous_people.setdefault(person_view.entity_id, person_view)
            recent_persons = [
                v
                for v in clusters_to_mention_views(
                    context.clusters_in_sentence(sentence.sentence_index - 1, _ALL_TYPES),
                    sentence.sentence_index - 1,
                    sentence.paragraph_index,
                )
                if v.entity_type == EntityType.PERSON
                and v.entity_id is not None
                and v.paragraph_index == sentence.paragraph_index
            ]
            if has_omitted_subject_trigger and (recent_persons or len(unique_previous_people) == 1):
                person = (
                    max(recent_persons, key=lambda v: v.end_char)
                    if recent_persons
                    else next(iter(unique_previous_people.values()))
                )
                for party in parties:
                    facts.append(
                        self._party_fact(
                            document=document,
                            sentence=sentence,
                            person=person,
                            party=party,
                            confidence=0.78,
                            evidence_scope="same_paragraph_omitted_subject",
                        )
                    )
                continue
            next_sentence = next(
                (
                    candidate_sentence
                    for candidate_sentence in document.sentences
                    if candidate_sentence.sentence_index == sentence.sentence_index + 1
                ),
                None,
            )
            if (
                next_sentence is None
                or next_sentence.paragraph_index - sentence.paragraph_index > 1
            ):
                continue
            persons = [
                v
                for v in clusters_to_mention_views(
                    context.clusters_in_sentence(next_sentence.sentence_index, _ALL_TYPES),
                    next_sentence.sentence_index,
                    next_sentence.paragraph_index,
                )
                if v.entity_type == EntityType.PERSON
                and v.entity_id is not None
                and v.start_char <= 20
            ]
            if not persons:
                continue
            person = min(persons, key=lambda v: v.start_char)
            for party in parties:
                facts.append(
                    self._party_fact(
                        document=document,
                        sentence=sentence,
                        person=person,
                        party=party,
                        confidence=0.92,
                        evidence_scope="adjacent_sentence",
                    )
                )
        return facts

    @staticmethod
    def _has_omitted_subject_party_trigger(
        parsed_words: list[ParsedWord],
        lowered: str,
    ) -> bool:
        if parsed_words:
            return any(
                (word.lemma or word.text).casefold() in OMITTED_SUBJECT_PARTY_LEMMAS
                for word in parsed_words
            )
        return any(marker in lowered for marker in OMITTED_SUBJECT_PARTY_MARKERS)

    @staticmethod
    def _party_fact(
        *,
        document: ArticleDocument,
        sentence: SentenceFragment,
        person: ClusterMentionView,
        party: ClusterMentionView,
        confidence: float,
        evidence_scope: str,
    ) -> Fact:
        assert person.entity_id is not None
        assert party.entity_id is not None
        return Fact(
            fact_id=FactID(
                stable_id(
                    "fact",
                    document.document_id,
                    FactType.PARTY_MEMBERSHIP,
                    person.entity_id,
                    party.entity_id,
                    str(sentence.sentence_index),
                    evidence_scope,
                )
            ),
            fact_type=FactType.PARTY_MEMBERSHIP,
            subject_entity_id=person.entity_id,
            object_entity_id=party.entity_id,
            value_text=party.canonical_name,
            value_normalized=party.normalized_name,
            confidence=confidence,
            time_scope=TimeScope.CURRENT,
            event_date=document.publication_date,
            evidence=EvidenceSpan(
                text=f"{person.canonical_name} ({party.canonical_name})",
                sentence_index=sentence.sentence_index,
                paragraph_index=sentence.paragraph_index,
                start_char=min(person.start_char, party.start_char),
                end_char=max(person.end_char, party.end_char),
            ),
            source_extractor="party_membership_relation_extractor",
            extraction_signal="discourse_window",
            evidence_scope=evidence_scope,
            party=party.canonical_name,
        )


def _sentence_time_scope(
    document: ArticleDocument,
    sentence: SentenceFragment,
    parsed_words: list[ParsedWord],
) -> TimeScope:
    from pipeline.grammar_signals import infer_time_scope_with_temporal_context

    return infer_time_scope_with_temporal_context(
        sentence.text,
        parsed_words,
        temporal_expressions=document.temporal_expressions,
        sentence_index=sentence.sentence_index,
        publication_date=document.publication_date,
    )
