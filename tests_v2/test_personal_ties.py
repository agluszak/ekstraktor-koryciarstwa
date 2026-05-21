from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.coreference import CoreferenceReferenceStage
from pipeline_v2.document import ArticleDocument
from pipeline_v2.fact_scoring import FactScoringStage
from pipeline_v2.ids import DocumentId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import CoreferenceSpanLink, Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.proxy import FamilyProxyCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.ties import PersonalTieCandidateStage
from pipeline_v2.types import FactKind, NerLabel, ReferenceKind, RelationshipDetail


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
        span=Span(text.index(name), text.index(name) + len(name)),
    )


def organization_span(text: str, name: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=name,
        label=NerLabel.ORGANIZATION,
        span=Span(text.index(name), text.index(name) + len(name)),
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
                    antecedent_span=Span(antecedent_start, antecedent_start + len("Jan Kowalski")),
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
    FactScoringStage().run(document)

    record = next(iter(document.store.fact_candidates.values())).to_fact_record()
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "subject", "entity_id": "proxy-1"},
        {"role": "object", "entity_id": "entity-0"},
        {"role": "relationship_detail", "value": "spouse"},
    )
    assert assessment.score >= 0.7


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

    record = next(iter(document.store.fact_candidates.values())).to_fact_record()

    assert record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "subject", "entity_id": "entity-0"},
        {"role": "object", "entity_id": "entity-1"},
        {"role": "relationship_detail", "value": "child"},
    )


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
    record = next(iter(document.store.fact_candidates.values())).to_fact_record()

    assert record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "subject", "entity_id": "entity-0"},
        {"role": "object", "entity_id": "entity-1"},
        {"role": "context", "value": "znajomy"},
    )


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

    assert tuple(document.store.fact_candidates.values()) == ()


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

    assert tuple(document.store.fact_candidates.values()) == ()


def test_personal_tie_stage_emits_multiple_kinship_ties_for_multiple_relatives() -> None:
    text = "Jan Kowalski, jego brat Piotr Kowalski i syn Adam Kowalski poszli do kina."
    document, _ = build_document(
        text,
        (
            person_span(text, "Jan Kowalski"),
            person_span(text, "Piotr Kowalski"),
            person_span(text, "Adam Kowalski"),
        ),
    )
    PersonalTieCandidateStage().run(document)

    records = [c.to_fact_record() for c in document.store.fact_candidates.values()]
    # There are 3 people, so we expect 3 combinations: (Jan, Piotr), (Jan, Adam), (Piotr, Adam)
    assert len(records) == 2
