from __future__ import annotations

from pipeline_v2.candidates import PersonalTieFactCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import ProducerId
from pipeline_v2.retrieval import SentenceEntity, SentenceEntityRetriever
from pipeline_v2.types import (
    EntityKind,
    ExplicitPatronageLemmaSignal,
    GroundingKind,
    LocalObjectSignal,
    LocalSubjectSignal,
    NamedKinshipLemmaSignal,
    PseudonymousSourceSignal,
    RelationshipDetail,
    Signal,
)


class PersonalTieCandidateStage:
    producer_id = ProducerId("personal_tie_candidate_stage_v2")

    _family_details_by_lemma = {
        "brat": RelationshipDetail.SIBLING,
        "córka": RelationshipDetail.CHILD,
        "dziewczyna": RelationshipDetail.SPOUSE,
        "kuzyn": RelationshipDetail.FAMILY,
        "kuzynka": RelationshipDetail.FAMILY,
        "matka": RelationshipDetail.PARENT,
        "mąż": RelationshipDetail.SPOUSE,
        "ojciec": RelationshipDetail.PARENT,
        "partner": RelationshipDetail.SPOUSE,
        "partnerka": RelationshipDetail.SPOUSE,
        "siostra": RelationshipDetail.SIBLING,
        "syn": RelationshipDetail.CHILD,
        "teść": RelationshipDetail.FAMILY,
        "teściowa": RelationshipDetail.FAMILY,
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
                    sentence=sentence,
                    sentence_id=sentence.id,
                    relationship_detail=family_detail,
                    signal=NamedKinshipLemmaSignal(lemma=family_detail.value),
                )
                continue
            patronage_lemma = self._patronage_detail(lemmas)
            if patronage_lemma is not None:
                self._add_explicit_tie(
                    document,
                    subject=people[0],
                    object_entity=people[1],
                    sentence=sentence,
                    sentence_id=sentence.id,
                    relationship_detail=None,
                    signal=ExplicitPatronageLemmaSignal(lemma=patronage_lemma),
                    context_text=patronage_lemma,
                )
        return document

    def _add_explicit_tie(
        self,
        document: ArticleDocument,
        *,
        subject: SentenceEntity,
        object_entity: SentenceEntity,
        sentence,
        sentence_id,
        relationship_detail: RelationshipDetail | None,
        signal: Signal,
        context_text: str | None = None,
    ) -> None:
        signals: list[Signal] = [
            signal,
            LocalSubjectSignal(),
            LocalObjectSignal(),
        ]
        pseudonymous_signal = self._pseudonymous_source_signal(document, sentence, subject)
        if pseudonymous_signal is not None:
            signals.append(pseudonymous_signal)
        document.store.add_fact_candidate(
            PersonalTieFactCandidate(
                id=document.store.next_fact_candidate_id(),
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
                signals=tuple(signals),
            )
        )

    def _pseudonymous_source_signal(
        self,
        document: ArticleDocument,
        sentence,
        subject: SentenceEntity,
    ) -> PseudonymousSourceSignal | None:
        lemmas = self._sentence_lemmas(document, sentence)
        if not (lemmas & {"osoba", "podpisać", "podpisany"}):
            return None
        subject_evidence = document.store.evidence_for_entity(subject.id)
        if not any(evidence.sentence_id == sentence.id for evidence in subject_evidence):
            return None
        if "podpis" not in sentence.text.casefold():
            return None
        return PseudonymousSourceSignal(cue_lemma="podpisać")

    def _observed_people(
        self,
        entities: tuple[SentenceEntity, ...],
        document: ArticleDocument,
    ) -> tuple[SentenceEntity, ...]:
        return tuple(
            entity
            for entity in entities
            if entity.kind == EntityKind.PERSON
            and document.store.entity_candidates[entity.id].grounding is GroundingKind.OBSERVED
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
