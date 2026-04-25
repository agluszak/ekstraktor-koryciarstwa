from __future__ import annotations

from pipeline.domain_types import (
    CandidateType,
    EntityID,
    FactID,
    FactType,
    TimeScope,
)
from pipeline.extraction_context import SentenceContext
from pipeline.models import (
    ArticleDocument,
    CandidateGraph,
    EntityCandidate,
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
from pipeline.secondary_fact_utils import (
    POLITICAL_ROLE_NAMES,
    SecondaryFactScorer,
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


class PoliticalProfileFactExtractor:
    POLITICAL_ROLE_NAMES = POLITICAL_ROLE_NAMES

    def extract(self, context: SentenceContext) -> list[Fact]:
        facts: list[Fact] = []
        governance_signal = _has_signal(
            context.parsed_words,
            context.lowered_text,
            APPOINTMENT_TRIGGER_LEMMAS | DISMISSAL_TRIGGER_LEMMAS,
            APPOINTMENT_TRIGGER_TEXTS | DISMISSAL_TRIGGER_TEXTS,
        )
        for person in context.persons:
            linked_party_ids: set[str] = set()
            parties = [
                *context.outgoing("person-affiliated-party", person.candidate_id),
                *context.parties,
            ]
            for party in parties:
                if party.candidate_id in linked_party_ids:
                    continue
                if context.edge_confidence(
                    "person-affiliated-party",
                    person.candidate_id,
                    party.candidate_id,
                ) is None and self._other_person_between(context, person, party):
                    continue
                linked_party_ids.add(party.candidate_id)
                score = SecondaryFactScorer.party_membership(
                    context,
                    person,
                    party,
                    governance_signal=governance_signal,
                )
                if score is None:
                    continue
                fact_type = (
                    FactType.FORMER_PARTY_MEMBERSHIP
                    if context.time_scope == TimeScope.FORMER
                    else FactType.PARTY_MEMBERSHIP
                )
                facts.append(
                    build_secondary_fact(
                        document=context.document,
                        sentence_context=context,
                        fact_type=fact_type,
                        subject=person,
                        object_candidate=party,
                        value_text=party.canonical_name,
                        value_normalized=party.normalized_name,
                        confidence=score.confidence,
                        score=score,
                        source_extractor="political_profile",
                        party=party.canonical_name,
                    )
                )

            for role in context.outgoing("person-has-role", person.candidate_id):
                role_name = role.normalized_name.lower()
                if role_name not in self.POLITICAL_ROLE_NAMES:
                    continue
                score = SecondaryFactScorer.political_office(
                    context,
                    person,
                    role,
                    governance_signal=governance_signal,
                )
                if score is None:
                    continue
                facts.append(
                    build_secondary_fact(
                        document=context.document,
                        sentence_context=context,
                        fact_type=FactType.POLITICAL_OFFICE,
                        subject=person,
                        object_candidate=role,
                        value_text=role.canonical_name,
                        value_normalized=role.normalized_name,
                        confidence=score.confidence,
                        score=score,
                        source_extractor="political_profile",
                        office_type=role.canonical_name,
                    )
                )

            candidacy_score = SecondaryFactScorer.candidacy(context, person)
            if candidacy_score is not None:
                facts.append(
                    build_secondary_fact(
                        document=context.document,
                        sentence_context=context,
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

    @staticmethod
    def _other_person_between(
        context: SentenceContext,
        person: EntityCandidate,
        party: EntityCandidate,
    ) -> bool:
        left = min(person.end_char, party.end_char)
        right = max(person.start_char, party.start_char)
        return any(
            candidate.candidate_id != person.candidate_id
            and candidate.start_char >= left
            and candidate.end_char <= right
            for candidate in context.persons
        )


class CrossSentencePartyFactBuilder:
    def build_cross_sentence_party_facts(
        self,
        document: ArticleDocument,
        candidate_graph: CandidateGraph,
    ) -> list[Fact]:
        candidates_by_sentence: dict[int, list[EntityCandidate]] = {}
        for candidate in candidate_graph.candidates:
            candidates_by_sentence.setdefault(candidate.sentence_index, []).append(candidate)

        facts: list[Fact] = []
        for sentence in document.sentences:
            sentence_candidates = candidates_by_sentence.get(sentence.sentence_index, [])
            parties = [
                candidate
                for candidate in sentence_candidates
                if candidate.candidate_type == CandidateType.POLITICAL_PARTY
                and candidate.entity_id is not None
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
            if any(
                candidate.candidate_type == CandidateType.PERSON
                for candidate in sentence_candidates
            ):
                continue
            previous_persons = [
                candidate
                for previous_sentence in document.sentences
                if previous_sentence.paragraph_index == sentence.paragraph_index
                and previous_sentence.sentence_index < sentence.sentence_index
                for candidate in candidates_by_sentence.get(previous_sentence.sentence_index, [])
                if candidate.candidate_type == CandidateType.PERSON
                and candidate.entity_id is not None
            ]
            unique_previous_people: dict[EntityID, EntityCandidate] = {}
            for person_candidate in previous_persons:
                assert person_candidate.entity_id is not None
                unique_previous_people.setdefault(person_candidate.entity_id, person_candidate)
            recent_persons = [
                candidate
                for candidate in candidates_by_sentence.get(sentence.sentence_index - 1, [])
                if candidate.candidate_type == CandidateType.PERSON
                and candidate.entity_id is not None
                and candidate.paragraph_index == sentence.paragraph_index
            ]
            if has_omitted_subject_trigger and (recent_persons or len(unique_previous_people) == 1):
                person = (
                    max(recent_persons, key=lambda candidate: candidate.end_char)
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
                candidate
                for candidate in candidates_by_sentence.get(next_sentence.sentence_index, [])
                if candidate.candidate_type == CandidateType.PERSON
                and candidate.entity_id is not None
                and candidate.start_char <= 20
            ]
            if not persons:
                continue
            person = min(persons, key=lambda candidate: candidate.start_char)
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
        person: EntityCandidate,
        party: EntityCandidate,
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
