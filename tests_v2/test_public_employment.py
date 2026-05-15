from __future__ import annotations

from pipeline_v2.document import ArticleDocument
from pipeline_v2.fact_scoring import FactScoringStage
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.ids import DocumentId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.public_employment import PublicEmploymentCandidateStage
from pipeline_v2.public_money import PublicMoneyCandidateStage
from pipeline_v2.roles import RoleCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import FactKind, NerLabel


class StaticEntityProvider:
    def __init__(self, entities: tuple[NamedEntitySpan, ...]) -> None:
        self.entities = entities

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return self.entities


def run_public_employment_stage(
    text: str,
    entities: tuple[NamedEntitySpan, ...],
    *,
    include_governance: bool = False,
    include_public_money: bool = False,
) -> ArticleDocument:
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
    RoleCandidateStage(morphology).run(document)
    if include_governance:
        GovernanceCandidateStage().run(document)
    PublicEmploymentCandidateStage().run(document)
    if include_public_money:
        PublicMoneyCandidateStage().run(document)
    FactScoringStage().run(document)
    return document


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


def test_public_employment_stage_emits_staffing_candidate_for_hire_into_advisory_role() -> None:
    text = "Urząd miasta zatrudnił Marka Nowaka jako doradcę burmistrza."
    document = run_public_employment_stage(
        text,
        (
            organization_span(text, "Urząd miasta"),
            person_span(text, "Marka Nowaka"),
        ),
    )

    record = next(iter(document.store.fact_candidates.values())).to_fact_record()
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.PUBLIC_EMPLOYMENT
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "person", "entity_id": "entity-1"},
        {"role": "organization", "entity_id": "entity-0"},
        {"role": "role", "entity_id": "entity-2"},
    )
    assert tuple(signal.name for signal in record.signals) == (
        "public_employment_lemma",
        "sentence_local_person",
        "sentence_local_organization",
        "sentence_local_role",
    )
    assert assessment.score >= 0.8


def test_public_employment_stage_emits_contract_like_staffing_candidate() -> None:
    text = "Starostwo podpisało z Anną Nowak umowę-zlecenie jako konsultantką projektu."
    document = run_public_employment_stage(
        text,
        (
            organization_span(text, "Starostwo"),
            person_span(text, "Anną Nowak"),
        ),
    )

    record = next(iter(document.store.fact_candidates.values())).to_fact_record()

    assert record.kind is FactKind.PUBLIC_EMPLOYMENT
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "person", "entity_id": "entity-1"},
        {"role": "organization", "entity_id": "entity-0"},
        {"role": "role", "entity_id": "entity-2"},
        {"role": "context", "value": "umowa-zlecenie"},
    )


def test_public_employment_stage_does_not_emit_for_governance_role_hire_overlap() -> None:
    text = "Spółka zatrudniła Jana Kowalskiego jako prezesa."
    document = run_public_employment_stage(
        text,
        (
            organization_span(text, "Spółka"),
            person_span(text, "Jana Kowalskiego"),
        ),
        include_governance=True,
    )

    records = tuple(
        candidate.to_fact_record() for candidate in document.store.fact_candidates.values()
    )

    assert tuple(record.kind for record in records) == (FactKind.GOVERNANCE_APPOINTMENT,)
    assert tuple(argument.to_json() for argument in records[0].arguments) == (
        {"role": "person", "entity_id": "entity-1"},
        {"role": "organization", "entity_id": "entity-0"},
        {"role": "role", "entity_id": "entity-2"},
    )


def test_public_employment_stage_does_not_emit_for_procurement_without_person() -> None:
    text = "Urząd podpisał umowę z firmą Alfa za 49 tys. zł."
    document = run_public_employment_stage(
        text,
        (
            organization_span(text, "Urząd"),
            organization_span(text, "Alfa"),
        ),
        include_public_money=True,
    )

    records = tuple(
        candidate.to_fact_record() for candidate in document.store.fact_candidates.values()
    )

    assert tuple(record.kind for record in records) == (FactKind.PUBLIC_CONTRACT,)
