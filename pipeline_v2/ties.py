from __future__ import annotations

from pipeline_v2.candidates import PersonalTieFactCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import FactCandidateId, ProducerId
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.types import GroundingKind, RelationshipDetail, positive_signal


class PersonalTieCandidateStage:
    producer_id = ProducerId("personal_tie_candidate_stage_v2")

    _family_details_by_lemma = {
        "brat": RelationshipDetail.SIBLING,
        "córka": RelationshipDetail.CHILD,
        "krewny": RelationshipDetail.FAMILY,
        "matka": RelationshipDetail.PARENT,
        "mąż": RelationshipDetail.SPOUSE,
        "ojciec": RelationshipDetail.PARENT,
        "rodzina": RelationshipDetail.FAMILY,
        "siostra": RelationshipDetail.SIBLING,
        "syn": RelationshipDetail.CHILD,
        "żona": RelationshipDetail.SPOUSE,
    }
    _patronage_lemmas = frozenset(
        {
            "człowiek",
            "polecenie",
            "powiązać",
            "rekomendacja",
            "współpracownik",
            "znajomy",
            "związany",
        }
    )

    def name(self) -> str:
        return "personal_tie_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        retriever = SentenceEntityRetriever(document.store)
        for sentence in document.store.sentences.values():
            people = self._observed_people(retriever.entities_for_sentence(sentence), document)
            if len(people) < 2:
                continue
            lemmas = self._sentence_lemmas(document, sentence)
            family_detail = self._family_detail(lemmas)
            if family_detail is not None:
                self._add_explicit_tie(
                    document,
                    subject=people[0],
                    object_entity=people[1],
                    sentence_id=sentence.id,
                    relationship_detail=family_detail,
                    signal_name="named_kinship_lemma",
                    signal_detail=family_detail.value,
                )
                continue
            patronage_lemma = self._patronage_detail(lemmas)
            if patronage_lemma is not None:
                self._add_explicit_tie(
                    document,
                    subject=people[0],
                    object_entity=people[1],
                    sentence_id=sentence.id,
                    relationship_detail=None,
                    signal_name="explicit_patronage_lemma",
                    signal_detail=patronage_lemma,
                    context_text=patronage_lemma,
                )
        return document

    def _add_explicit_tie(
        self,
        document: ArticleDocument,
        *,
        subject: SentenceEntity,
        object_entity: SentenceEntity,
        sentence_id,
        relationship_detail: RelationshipDetail | None,
        signal_name: str,
        signal_detail: str,
        context_text: str | None = None,
    ) -> None:
        document.store.add_fact_candidate(
            PersonalTieFactCandidate(
                id=FactCandidateId(f"fact-{len(document.store.fact_candidates)}"),
                subject_entity_id=subject.id,
                object_entity_id=object_entity.id,
                evidence_ids=tuple(
                    evidence.id
                    for evidence in document.store.evidence_for_entity(subject.id)
                    if evidence.sentence_id == sentence_id
                )
                or tuple(
                    evidence.id
                    for evidence in document.store.evidence_for_entity(object_entity.id)
                    if evidence.sentence_id == sentence_id
                ),
                source=self.producer_id,
                relationship_detail=relationship_detail,
                context_text=context_text,
                signals=(
                    positive_signal(signal_name, details=signal_detail),
                    positive_signal("sentence_local_subject"),
                    positive_signal("sentence_local_object"),
                ),
            )
        )

    def _observed_people(
        self,
        entities: tuple[SentenceEntity, ...],
        document: ArticleDocument,
    ) -> tuple[SentenceEntity, ...]:
        return tuple(
            entity
            for entity in entities
            if document.store.entity_candidates[entity.id].grounding is GroundingKind.OBSERVED
        )

    def _sentence_lemmas(self, document: ArticleDocument, sentence) -> frozenset[str]:
        lemmas: set[str] = set()
        for token_id in sentence.token_ids:
            token = document.store.tokens[token_id]
            for analysis in token.morph:
                lemmas.add(analysis.lemma)
        return frozenset(lemmas)

    def _family_detail(self, lemmas: frozenset[str]) -> RelationshipDetail | None:
        for lemma, relationship_detail in self._family_details_by_lemma.items():
            if lemma in lemmas:
                return relationship_detail
        return None

    def _patronage_detail(self, lemmas: frozenset[str]) -> str | None:
        matched = tuple(sorted(lemmas & self._patronage_lemmas))
        if not matched:
            return None
        return matched[0]
