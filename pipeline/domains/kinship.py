from __future__ import annotations

from dataclasses import dataclass

from pipeline.domain_lexicons import KINSHIP_BY_LEMMA
from pipeline.domain_types import (
    CandidateID,
    CandidateType,
    EntityID,
    EntityType,
    FactID,
    FactType,
    IdentityHypothesisStatus,
    KinshipDetail,
    RelationshipType,
    TimeScope,
)
from pipeline.extraction_context import ExtractionContext, clusters_to_sentence_candidates
from pipeline.models import (
    ArticleDocument,
    EntityCandidate,
    EntityCluster,
    EvidenceSpan,
    Fact,
    IdentityResolutionMetadata,
    ParsedWord,
    SentenceFragment,
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


@dataclass(frozen=True, slots=True)
class KinshipTieEvidence:
    subject: EntityCandidate
    target: EntityCandidate
    kinship_detail: KinshipDetail
    confidence: float
    extraction_signal: str
    evidence_scope: str
    sentence: SentenceFragment
    possible_identity_matches: tuple[EntityID, ...] = ()
    identity_resolution: IdentityResolutionMetadata | None = None


class KinshipTieBuilder:
    def build(
        self,
        document: ArticleDocument,
        context: ExtractionContext,
    ) -> list[Fact]:
        evidence_items: list[KinshipTieEvidence] = []
        for sentence in document.sentences:
            sentence_candidates = clusters_to_sentence_candidates(
                context.clusters_in_sentence(sentence.sentence_index, _ALL_TYPES),
                sentence.sentence_index,
                sentence.paragraph_index,
            )
            evidence_items.extend(
                self._direct_sentence_ties(
                    document=document,
                    sentence=sentence,
                    sentence_candidates=sentence_candidates,
                )
            )
        candidates_by_entity_id = _build_candidates_by_entity_id(document.clusters)
        evidence_items.extend(self._identity_backed_proxy_ties(document, candidates_by_entity_id))
        return [self._fact(document, evidence) for evidence in evidence_items]

    def _direct_sentence_ties(
        self,
        *,
        document: ArticleDocument,
        sentence: SentenceFragment,
        sentence_candidates: list[EntityCandidate],
    ) -> list[KinshipTieEvidence]:
        persons = [
            candidate
            for candidate in sentence_candidates
            if candidate.candidate_type == CandidateType.PERSON and candidate.entity_id is not None
        ]
        if len(persons) < 2:
            return []
        parsed_words = document.parsed_sentences.get(sentence.sentence_index, [])
        if not parsed_words:
            return self._text_fallback_ties(sentence, persons)

        ties: list[KinshipTieEvidence] = []
        for word in parsed_words:
            kinship_detail = self._kinship_detail(word)
            if kinship_detail is None:
                continue
            subject = self._subject_for_kinship_word(word, persons)
            target = self._target_for_kinship_word(word, parsed_words, persons)
            if subject is None or target is None:
                continue
            if subject.entity_id == target.entity_id:
                continue
            ties.append(
                KinshipTieEvidence(
                    subject=subject,
                    target=target,
                    kinship_detail=kinship_detail,
                    confidence=0.88,
                    extraction_signal="kinship_apposition",
                    evidence_scope="same_sentence",
                    sentence=sentence,
                )
            )
        return ties

    @staticmethod
    def _subject_for_kinship_word(
        kinship_word: ParsedWord,
        persons: list[EntityCandidate],
    ) -> EntityCandidate | None:
        preceding = [
            person
            for person in persons
            if person.end_char <= kinship_word.start and kinship_word.start - person.end_char <= 12
        ]
        if preceding:
            return max(preceding, key=lambda person: person.end_char)
        return None

    def _target_for_kinship_word(
        self,
        kinship_word: ParsedWord,
        parsed_words: list[ParsedWord],
        persons: list[EntityCandidate],
    ) -> EntityCandidate | None:
        descendants = self._descendant_indices(parsed_words, kinship_word.index)
        after_candidates = [
            person
            for person in persons
            if person.start_char >= kinship_word.end and person.start_char - kinship_word.end <= 120
        ]
        dependency_matches = [
            person
            for person in after_candidates
            if self._candidate_overlaps_word_indices(person, parsed_words, descendants)
        ]
        if dependency_matches:
            return min(dependency_matches, key=lambda person: person.start_char)
        if after_candidates:
            return min(after_candidates, key=lambda person: person.start_char)
        return None

    @staticmethod
    def _descendant_indices(parsed_words: list[ParsedWord], root_index: int) -> set[int]:
        descendants: set[int] = set()
        frontier = {root_index}
        while frontier:
            parent = frontier.pop()
            children = {word.index for word in parsed_words if word.head == parent}
            children -= descendants
            descendants.update(children)
            frontier.update(children)
        return descendants

    @staticmethod
    def _candidate_overlaps_word_indices(
        candidate: EntityCandidate,
        parsed_words: list[ParsedWord],
        word_indices: set[int],
    ) -> bool:
        return any(
            word.index in word_indices
            and (
                candidate.start_char <= word.start < candidate.end_char
                or word.start <= candidate.start_char < word.end
            )
            for word in parsed_words
        )

    def _text_fallback_ties(
        self,
        sentence: SentenceFragment,
        persons: list[EntityCandidate],
    ) -> list[KinshipTieEvidence]:
        lowered = sentence.text.casefold()
        ties: list[KinshipTieEvidence] = []
        for surface, kinship_detail in KINSHIP_BY_LEMMA.items():
            anchor = lowered.find(surface)
            if anchor < 0:
                continue
            subject = max(
                (person for person in persons if person.end_char <= anchor),
                key=lambda person: person.end_char,
                default=None,
            )
            target = min(
                (person for person in persons if person.start_char >= anchor + len(surface)),
                key=lambda person: person.start_char,
                default=None,
            )
            if subject is None or target is None or subject.entity_id == target.entity_id:
                continue
            between_subject = lowered[subject.end_char : anchor]
            if len(between_subject) > 12 or "," not in between_subject:
                continue
            ties.append(
                KinshipTieEvidence(
                    subject=subject,
                    target=target,
                    kinship_detail=kinship_detail,
                    confidence=0.76,
                    extraction_signal="kinship_apposition_text",
                    evidence_scope="same_sentence",
                    sentence=sentence,
                )
            )
        return ties

    def _identity_backed_proxy_ties(
        self,
        document: ArticleDocument,
        candidates_by_entity_id: dict[EntityID, EntityCandidate],
    ) -> list[KinshipTieEvidence]:
        facts_by_proxy = {
            fact.subject_entity_id: fact
            for fact in document.facts
            if fact.fact_type == FactType.PERSONAL_OR_POLITICAL_TIE
            and fact.relationship_type == RelationshipType.FAMILY
            and fact.kinship_detail is not None
        }
        ties: list[KinshipTieEvidence] = []
        for hypothesis in document.identity_hypotheses:
            if hypothesis.status not in {
                IdentityHypothesisStatus.PROBABLE,
                IdentityHypothesisStatus.CONFIRMED,
            }:
                continue
            left_fact = facts_by_proxy.get(hypothesis.left_entity_id)
            right_fact = facts_by_proxy.get(hypothesis.right_entity_id)
            proxy_fact = left_fact or right_fact
            if proxy_fact is None or proxy_fact.object_entity_id is None:
                continue
            kinship_detail = proxy_fact.kinship_detail
            if kinship_detail is None:
                continue
            proxy_entity_id = (
                hypothesis.left_entity_id if left_fact is not None else hypothesis.right_entity_id
            )
            matched_entity_id = (
                hypothesis.right_entity_id
                if proxy_entity_id == hypothesis.left_entity_id
                else hypothesis.left_entity_id
            )
            subject_id = (
                matched_entity_id
                if hypothesis.status == IdentityHypothesisStatus.CONFIRMED
                else proxy_entity_id
            )
            subject = candidates_by_entity_id.get(subject_id)
            target = candidates_by_entity_id.get(proxy_fact.object_entity_id)
            if subject is None or target is None or subject.entity_id == target.entity_id:
                continue
            sentence = self._sentence_for_evidence(document, proxy_fact.evidence)
            if sentence is None or not self._same_or_adjacent_paragraph_sentence(
                proxy_fact.evidence,
                sentence,
            ):
                continue
            identity_resolution = None
            possible_matches: tuple[EntityID, ...] = ()
            confidence = min(0.78, hypothesis.confidence)
            if hypothesis.status == IdentityHypothesisStatus.CONFIRMED:
                identity_resolution = IdentityResolutionMetadata(
                    matched_entity_id=matched_entity_id,
                    confidence=hypothesis.confidence,
                    status=hypothesis.status,
                )
            else:
                possible_matches = (matched_entity_id,)
                confidence = min(confidence, 0.68)
            ties.append(
                KinshipTieEvidence(
                    subject=subject,
                    target=target,
                    kinship_detail=kinship_detail,
                    confidence=confidence,
                    extraction_signal="identity_hypothesis",
                    evidence_scope="same_paragraph_adjacent_sentence",
                    sentence=sentence,
                    possible_identity_matches=possible_matches,
                    identity_resolution=identity_resolution,
                )
            )
        return ties

    @staticmethod
    def _sentence_for_evidence(
        document: ArticleDocument,
        evidence: EvidenceSpan,
    ) -> SentenceFragment | None:
        if evidence.sentence_index is None:
            return None
        return next(
            (
                sentence
                for sentence in document.sentences
                if sentence.sentence_index == evidence.sentence_index
            ),
            None,
        )

    @staticmethod
    def _same_or_adjacent_paragraph_sentence(
        evidence: EvidenceSpan,
        sentence: SentenceFragment,
    ) -> bool:
        if (
            evidence.paragraph_index is not None
            and evidence.paragraph_index != sentence.paragraph_index
        ):
            return False
        if evidence.sentence_index is None:
            return False
        return abs(evidence.sentence_index - sentence.sentence_index) <= 1

    @staticmethod
    def _kinship_detail(word: ParsedWord) -> KinshipDetail | None:
        return KINSHIP_BY_LEMMA.get(word.lemma.casefold()) or KINSHIP_BY_LEMMA.get(
            word.text.casefold()
        )

    @staticmethod
    def _fact(document: ArticleDocument, evidence: KinshipTieEvidence) -> Fact:
        fact_id = FactID(
            stable_id(
                "fact",
                document.document_id,
                FactType.PERSONAL_OR_POLITICAL_TIE,
                evidence.subject.entity_id or evidence.subject.candidate_id,
                evidence.target.entity_id or evidence.target.candidate_id,
                evidence.kinship_detail.value,
                str(evidence.sentence.sentence_index),
                evidence.extraction_signal,
            )
        )
        return Fact(
            fact_id=fact_id,
            fact_type=FactType.PERSONAL_OR_POLITICAL_TIE,
            subject_entity_id=EntityID(evidence.subject.entity_id or evidence.subject.candidate_id),
            object_entity_id=EntityID(evidence.target.entity_id or evidence.target.candidate_id),
            value_text=evidence.kinship_detail.value,
            value_normalized=evidence.kinship_detail.value,
            time_scope=TimeScope.CURRENT,
            event_date=document.publication_date,
            confidence=evidence.confidence,
            evidence=EvidenceSpan(
                text=evidence.sentence.text,
                sentence_index=evidence.sentence.sentence_index,
                paragraph_index=evidence.sentence.paragraph_index,
                start_char=evidence.sentence.start_char,
                end_char=evidence.sentence.end_char,
            ),
            relationship_type=RelationshipType.FAMILY,
            kinship_detail=evidence.kinship_detail,
            identity_resolution=evidence.identity_resolution,
            possible_identity_matches=list(evidence.possible_identity_matches),
            source_extractor="kinship_tie_builder",
            extraction_signal=evidence.extraction_signal,
            evidence_scope=evidence.evidence_scope,
        )


def _cluster_to_candidate(cluster: EntityCluster) -> EntityCandidate:
    mention = cluster.mentions[0] if cluster.mentions else None
    entity_id = next((m.entity_id for m in cluster.mentions if m.entity_id), None)
    return EntityCandidate(
        candidate_id=CandidateID(str(cluster.cluster_id)),
        entity_id=entity_id,
        candidate_type=CandidateType(cluster.entity_type),
        canonical_name=cluster.canonical_name,
        normalized_name=cluster.normalized_name,
        sentence_index=mention.sentence_index if mention else 0,
        paragraph_index=mention.paragraph_index if mention else 0,
        start_char=mention.start_char if mention else 0,
        end_char=mention.end_char if mention else 0,
        source="cluster",
        organization_kind=cluster.organization_kind,
        role_kind=cluster.role_kind,
        role_modifier=cluster.role_modifier,
        is_proxy_person=cluster.is_proxy_person,
        kinship_detail=cluster.kinship_detail,
        ner_label=mention.ner_label if mention else None,
    )


def _build_candidates_by_entity_id(
    clusters: list[EntityCluster],
) -> dict[EntityID, EntityCandidate]:
    result: dict[EntityID, EntityCandidate] = {}
    for cluster in clusters:
        entity_id = next((m.entity_id for m in cluster.mentions if m.entity_id), None)
        if entity_id is not None and entity_id not in result:
            result[entity_id] = _cluster_to_candidate(cluster)
    return result
