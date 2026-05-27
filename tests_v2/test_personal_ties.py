from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.coreference import CoreferenceReferenceStage
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import DocumentId
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import CoreferenceSpanLink, Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.proxy import FamilyProxyCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.ties import PersonalTieCandidateStage
from pipeline_v2.types import FactKind, NerLabel, ReferenceKind, RelationshipDetail
from tests_v2.materialized import (
    entity_hint_for_role,
    fact_records,
    first_fact_record,
    span_of,
    text_argument,
)


@dataclass(frozen=True, slots=True)
class StaticEntityProvider:
    entities: tuple[NamedEntitySpan, ...]

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return self.entities


@dataclass(frozen=True, slots=True)
class StaticCoreferenceProvider:
    coreference_links: tuple[CoreferenceSpanLink, ...]

    def links(self, text: str) -> tuple[CoreferenceSpanLink, ...]:
        _ = text
        return self.coreference_links


def build_document(
    text: str,
    entities: tuple[NamedEntitySpan, ...],
) -> tuple[ArticleDocument, Morfeusz2MorphologyAdapter]:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=text,
        paragraphs=(text,),
    )
    morphology = Morfeusz2MorphologyAdapter()
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage(morphology).run(document)
    NamedEntityCandidateStage(
        provider=StaticEntityProvider(entities),
        morphology=morphology,
    ).run(document)
    return document, morphology


def person_span(text: str, name: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=name,
        label=NerLabel.PERSON,
        span=span_of(text, name),
    )


def organization_span(text: str, name: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=name,
        label=NerLabel.ORGANIZATION,
        span=span_of(text, name),
    )


def test_personal_tie_stage_emits_proxy_family_tie_from_family_reference() -> None:
    text = "Jan Kowalski został burmistrzem. Jego żona pracuje w urzędzie."
    document, morphology = build_document(text, (person_span(text, "Jan Kowalski"),))
    antecedent_start = text.index("Jan Kowalski")
    reference_start = text.index("Jego żona")

    CoreferenceReferenceStage(
        provider=StaticCoreferenceProvider(
            (
                CoreferenceSpanLink(
                    antecedent_text="Jan Kowalski",
                    antecedent_span=Span(
                        antecedent_start,
                        antecedent_start + len("Jan Kowalski"),
                    ),
                    reference_text="Jego żona",
                    reference_span=Span(reference_start, reference_start + len("Jego żona")),
                    reference_kind=ReferenceKind.PROXY_FAMILY_PHRASE,
                    relationship_detail=RelationshipDetail.SPOUSE,
                ),
            )
        ),
        morphology=morphology,
    ).run(document)
    FamilyProxyCandidateStage().run(document)
    PersonalTieCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.KINSHIP_TIE
    assert entity_hint_for_role(document, record, "subject") == "spouse of Jan Kowalski"
    assert entity_hint_for_role(document, record, "object") == "Jan Kowalski"
    assert text_argument(record, "relationship_detail") == "spouse"
    assert assessment.score >= 0.3


def test_personal_tie_stage_emits_named_kinship_tie_from_two_people_and_family_lemma() -> None:
    text = "Marek Kowalski, syn Jana Kowalskiego, pracuje w urzędzie."
    document, _morphology = build_document(
        text,
        (
            person_span(text, "Marek Kowalski"),
            person_span(text, "Jana Kowalskiego"),
        ),
    )

    PersonalTieCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)

    records = fact_records(document)
    kinship_records = [r for r in records if r.kind == FactKind.KINSHIP_TIE]
    assert len(kinship_records) >= 1
    record = kinship_records[0]

    assert record.kind is FactKind.KINSHIP_TIE
    assert entity_hint_for_role(document, record, "subject") == "Marek Kowalski"
    assert entity_hint_for_role(document, record, "object") == "Jana Kowalskiego"
    assert text_argument(record, "relationship_detail") == "child"


def test_personal_tie_stage_emits_explicit_patronage_tie_from_two_people() -> None:
    text = "Piotr Nowak, znajomy Jana Kowalskiego, dostał posadę w urzędzie."
    document, _morphology = build_document(
        text,
        (
            person_span(text, "Piotr Nowak"),
            person_span(text, "Jana Kowalskiego"),
        ),
    )

    PersonalTieCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)
    records = [
        record
        for record in fact_records(document)
        if record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
    ]
    assert records
    record = records[0]

    assert entity_hint_for_role(document, record, "subject") == "Piotr Nowak"
    assert entity_hint_for_role(document, record, "object") == "Jana Kowalskiego"
    assert text_argument(record, "context") == "znajomy"


def test_personal_tie_stage_does_not_emit_for_plain_two_person_cooccurrence() -> None:
    text = "Jan Kowalski skrytykował Marka Nowaka za decyzję rady miasta."
    document, _morphology = build_document(
        text,
        (
            person_span(text, "Jan Kowalski"),
            person_span(text, "Marka Nowaka"),
        ),
    )

    PersonalTieCandidateStage().run(document)

    assert fact_records(document) == ()


def test_personal_tie_stage_does_not_emit_patronage_tie_for_person_and_organization() -> None:
    text = "Jan Kowalski, człowiek PiS, zabrał głos na sesji rady miasta."
    document, _morphology = build_document(
        text,
        (
            person_span(text, "Jan Kowalski"),
            organization_span(text, "PiS"),
        ),
    )

    PersonalTieCandidateStage().run(document)

    assert fact_records(document) == ()


def test_personal_tie_stage_does_not_expand_czlowiek_into_window_people() -> None:
    text = (
        "Stanisław Mazur i Andrzej Kloc będą kierować funduszem. "
        "W radzie ostał się jeszcze człowiek z poprzedniego nadania — Jerzy Szwaj."
    )
    document, _morphology = build_document(
        text,
        (
            person_span(text, "Stanisław Mazur"),
            person_span(text, "Andrzej Kloc"),
            person_span(text, "Jerzy Szwaj"),
        ),
    )

    PersonalTieCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)

    personal_ties = [
        r for r in fact_records(document) if r.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
    ]
    # "człowiek" in second sentence should not pull in Mazur/Kloc from first sentence via window
    assert not any(
        {
            entity_hint_for_role(document, r, "subject"),
            entity_hint_for_role(document, r, "object"),
        }
        == {"Stanisław Mazur", "Jerzy Szwaj"}
        or {
            entity_hint_for_role(document, r, "subject"),
            entity_hint_for_role(document, r, "object"),
        }
        == {"Andrzej Kloc", "Jerzy Szwaj"}
        for r in personal_ties
    )


def test_personal_tie_stage_uses_previous_sentence_person_for_collaborator_tie() -> None:
    text = (
        "Jarosław Hodura od grudnia jest prezesem Grupy Hoteli WAM. "
        "Były szef biura europoselskiego Klicha i jego wieloletni przyjaciel trafił do zarządu."
    )
    document, _morphology = build_document(
        text,
        (
            person_span(text, "Jarosław Hodura"),
            person_span(text, "Klicha"),
            organization_span(text, "Grupy Hoteli WAM"),
        ),
    )

    PersonalTieCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)

    records = [
        record
        for record in fact_records(document)
        if record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
    ]
    assert records
    assert any(
        {
            entity_hint_for_role(document, record, "subject"),
            entity_hint_for_role(document, record, "object"),
        }
        == {"Jarosław Hodura", "Klicha"}
        for record in records
    )


def test_patronage_complaint_uses_adjacent_sentence_people_and_keeps_evidence() -> None:
    text = (
        "W mieście trwa kolesiostwo i rozdawanie posad. "
        "Dorota Połedniok publicznie oskarżyła Jacka Guzego o układ."
    )
    document, _morphology = build_document(
        text,
        (
            person_span(text, "Dorota Połedniok"),
            person_span(text, "Jacka Guzego"),
        ),
    )

    PersonalTieCandidateStage().run(document)
    complaint_events = [
        event
        for event in document.store.event_candidates.values()
        if event.kind in {FactKind.PATRONAGE_ALLEGATION, FactKind.PATRONAGE_NETWORK_TIE}
    ]
    assert complaint_events
    assert all(event.trigger_evidence_id is not None for event in complaint_events)
    assert all(event.evidence_ids for event in complaint_events)

    ProbabilisticInferenceStage().run(document)
    complaint_records = [
        record
        for record in fact_records(document)
        if record.kind in {FactKind.PATRONAGE_ALLEGATION, FactKind.PATRONAGE_NETWORK_TIE}
    ]
    assert complaint_records

    allegation = next(
        record for record in complaint_records if record.kind is FactKind.PATRONAGE_ALLEGATION
    )
    network = next(
        record for record in complaint_records if record.kind is FactKind.PATRONAGE_NETWORK_TIE
    )
    assert entity_hint_for_role(document, allegation, "complainant") == "Dorota Połedniok"
    assert entity_hint_for_role(document, allegation, "target") == "Jacka Guzego"
    assert entity_hint_for_role(document, network, "subject") == "Dorota Połedniok"
    assert entity_hint_for_role(document, network, "object") == "Jacka Guzego"


def test_patronage_complaint_ignores_single_weak_person_without_institution() -> None:
    text = "Bytomski alarmuje o kolesiostwie."
    document, _morphology = build_document(
        text,
        (person_span(text, "Bytomski"),),
    )

    PersonalTieCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)

    complaint_records = [
        record
        for record in fact_records(document)
        if record.kind in {FactKind.PATRONAGE_ALLEGATION, FactKind.PATRONAGE_NETWORK_TIE}
    ]
    assert complaint_records == []
