from __future__ import annotations

from pipeline_v2.document import ArticleDocument
from pipeline_v2.fact_scoring import FactScoringStage
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.ids import DocumentId, EntityCandidateId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.nominal_coreference import NominalKinshipCandidateStage
from pipeline_v2.public_employment import PublicEmploymentCandidateStage
from pipeline_v2.public_money import PublicMoneyCandidateStage
from pipeline_v2.roles import RoleCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import (
    FactKind,
    InferredPublicOrganizationSignal,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    LocationContextSignal,
    NerLabel,
    PublicEmploymentLemmaSignal,
)
from tests_v2.materialized import fact_records, first_fact_record


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
    include_nominal_kinship: bool = False,
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
    if include_nominal_kinship:
        NominalKinshipCandidateStage().run(document)
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


def location_span(text: str, name: str) -> NamedEntitySpan:
    return NamedEntitySpan(
        text=name,
        label=NerLabel.LOCATION,
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

    candidate = next(
        candidate
        for candidate in fact_records(document)
        if candidate.kind is FactKind.PUBLIC_EMPLOYMENT
    )
    record = candidate
    assessment = next(
        item.assessment
        for item in document.fact_assessments
        if item.materialized_fact_id == candidate.id
    )

    assert record.kind is FactKind.PUBLIC_EMPLOYMENT
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "person", "entity_id": "entity-1"},
        {"role": "organization", "entity_id": "entity-0"},
        {"role": "role", "entity_id": "entity-2"},
    )
    assert set(record.signals) == {
        PublicEmploymentLemmaSignal(lemma="zatrudnić"),
        LocalPersonSignal(),
        LocalOrganizationSignal(),
        LocalRoleSignal(),
    }
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

    record = first_fact_record(document)

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

    records = fact_records(document)

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

    records = fact_records(document)

    assert tuple(record.kind for record in records) == (FactKind.PUBLIC_CONTRACT,)


def test_public_employment_stage_rejects_active_nominative_subject() -> None:
    # "Tomasz Kościelniak zatrudnił partnerkę w urzędzie."
    # Tomasz Kościelniak is Nominative and the sentence has an active verb "zatrudnił".
    # Therefore he is the subject/employer and should be rejected as the employee.
    text = "Tomasz Kościelniak zatrudnił partnerkę w urzędzie."
    document = run_public_employment_stage(
        text,
        (
            person_span(text, "Tomasz Kościelniak"),
            organization_span(text, "urzędzie"),
        ),
    )
    records = fact_records(document)
    # The fact candidate should be empty because the person entity is the active subject,
    # and "partnerkę" is unnamed (so not a person candidate yet).
    assert len(records) == 0


def test_public_employment_stage_binds_possessive_kinship_proxy_as_hired_person() -> None:
    text = "Tomasz Kościelniak zatrudnił swojego przyszłego teścia w Urzędzie Stanu Cywilnego."
    document = run_public_employment_stage(
        text,
        (
            person_span(text, "Tomasz Kościelniak"),
            organization_span(text, "Urzędzie Stanu Cywilnego"),
        ),
        include_nominal_kinship=True,
    )

    candidate = next(
        candidate
        for candidate in fact_records(document)
        if candidate.kind is FactKind.PUBLIC_EMPLOYMENT
    )
    record = candidate
    person_argument = next(
        argument for argument in record.arguments if argument.to_json()["role"] == "person"
    )
    proxy_entity = document.store.entity_candidates[
        EntityCandidateId(person_argument.to_json()["entity_id"])
    ]
    assessment = next(
        item.assessment
        for item in document.fact_assessments
        if item.materialized_fact_id == candidate.id
    )

    assert record.kind is FactKind.PUBLIC_EMPLOYMENT
    assert proxy_entity.canonical_hint == "teść of Tomasz Kościelniak"
    assert assessment.score >= 0.8


def test_public_employment_stage_handles_impersonal_passive_hiring_sentence() -> None:
    text = (
        "Na początku lipca w samorządzie Gminy Poczesna zatrudniono Rafała Dobosza "
        "na stanowisku pomocy administracyjnej."
    )
    document = run_public_employment_stage(
        text,
        (
            organization_span(text, "Gminy Poczesna"),
            person_span(text, "Rafała Dobosza"),
        ),
    )

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.PUBLIC_EMPLOYMENT
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "person", "entity_id": "entity-1"},
        {"role": "organization", "entity_id": "entity-0"},
        {"role": "role", "entity_id": "entity-2"},
    )
    assert assessment.score >= 0.8


def test_public_employment_stage_materializes_public_org_from_samorzad_and_location() -> None:
    text = (
        "Kontrowersje w gminy Poczesna. "
        "Na początku lipca w samorządzie zatrudniono Rafała Dobosza "
        "na stanowisku pomocy administracyjnej."
    )
    document = run_public_employment_stage(
        text,
        (
            location_span(text, "gminy Poczesna"),
            person_span(text, "Rafała Dobosza"),
        ),
    )

    candidate = first_fact_record(document)
    record = candidate
    organization_id = EntityCandidateId(
        next(
            argument.to_json()["entity_id"]
            for argument in record.arguments
            if argument.to_json()["role"] == "organization"
        )
    )

    assert record.kind is FactKind.PUBLIC_EMPLOYMENT
    organization = document.store.entity_candidates[organization_id]
    assert organization.canonical_hint == "samorządzie"
    assert InferredPublicOrganizationSignal(head_lemma="samorząd") in record.signals
    assert LocationContextSignal(distance=1) in record.signals
