from __future__ import annotations

from pipeline_v2.anti_corruption import AntiCorruptionCandidateStage
from pipeline_v2.document import ArticleDocument
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.ids import DocumentId
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.party import PartyCandidateStage
from pipeline_v2.roles import RoleCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import EntityKind, FactKind, NerLabel
from tests_v2.materialized import (
    argument_roles,
    entity_argument,
    entity_hint_for_role,
    fact_record_by_id,
    fact_records,
    first_fact_record,
    text_argument,
)


class StaticEntityProvider:
    def __init__(self, entities: tuple[NamedEntitySpan, ...]) -> None:
        self.entities = entities

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return self.entities


def run_anti_corruption_pipeline(
    text: str,
    entities: tuple[NamedEntitySpan, ...] = (),
    *,
    include_governance: bool = False,
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
    PartyCandidateStage(morphology).run(document)
    if include_governance:
        RoleCandidateStage(morphology).run(document)
        GovernanceCandidateStage().run(document)
    AntiCorruptionCandidateStage().run(document)
    ProbabilisticInferenceStage().run(document)
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


def test_anti_corruption_stage_emits_referral_with_party_actor_context() -> None:
    text = "Radni PiS zapowiedzieli zawiadomienie do CBA w sprawie zatrudnienia Jana Nowaka."
    document = run_anti_corruption_pipeline(
        text,
        (
            organization_span(text, "CBA"),
            person_span(text, "Jana Nowaka"),
        ),
        include_governance=True,
    )

    records = fact_records(document)
    referral_record = next(
        record for record in records if record.kind is FactKind.ANTI_CORRUPTION_REFERRAL
    )
    referral_assessment = next(
        assessment
        for assessment in document.fact_assessments
        if fact_record_by_id(document, assessment.materialized_fact_id).kind
        is FactKind.ANTI_CORRUPTION_REFERRAL
    )
    party_entity = next(
        entity
        for entity in document.store.entity_candidates.values()
        if entity.kind is EntityKind.POLITICAL_PARTY
    )

    assert entity_argument(referral_record, "complainant") == party_entity.id
    assert entity_hint_for_role(document, referral_record, "target") == "Jana Nowaka"
    assert entity_hint_for_role(document, referral_record, "institution") == "CBA"
    assert text_argument(referral_record, "context") == "w sprawie zatrudnienia Jana Nowaka"
    assert referral_assessment.assessment.score >= 0.6
    governance_records = tuple(
        record
        for record in records
        if record.kind in {FactKind.PUBLIC_ROLE_APPOINTMENT, FactKind.PUBLIC_ROLE_END}
    )
    party_hint = party_entity.canonical_hint
    assert all(
        "organization" not in argument_roles(record)
        or entity_hint_for_role(document, record, "organization") != party_hint
        for record in governance_records
    )


def test_anti_corruption_stage_emits_impersonal_referral_to_prosecutor() -> None:
    text = "Sprawę skierowano do prokuratury po kontroli w urzędzie."
    document = run_anti_corruption_pipeline(text)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.ANTI_CORRUPTION_REFERRAL
    assert text_argument(record, "institution") == "prokuratury"
    assert assessment.score >= 0.5


def test_anti_corruption_stage_emits_investigation_for_nik_control() -> None:
    text = "NIK wszczęła kontrolę w spółce Wodkan."
    document = run_anti_corruption_pipeline(
        text,
        (
            organization_span(text, "NIK"),
            organization_span(text, "Wodkan"),
        ),
    )

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.ANTI_CORRUPTION_INVESTIGATION
    assert entity_hint_for_role(document, record, "target") == "Wodkan"
    assert entity_hint_for_role(document, record, "institution") == "NIK"
    assert assessment.score >= 0.6


def test_anti_corruption_stage_emits_investigation_with_text_institution_fallback() -> None:
    text = "Prokuratura wszczęła śledztwo w sprawie Jana Nowaka."
    document = run_anti_corruption_pipeline(text, (person_span(text, "Jana Nowaka"),))

    record = first_fact_record(document)

    assert record.kind is FactKind.ANTI_CORRUPTION_INVESTIGATION
    assert entity_hint_for_role(document, record, "target") == "Jana Nowaka"
    assert text_argument(record, "institution") == "Prokuratura"
    assert text_argument(record, "context") == "w sprawie Jana Nowaka"


def test_anti_corruption_stage_does_not_emit_referral_for_ordinary_cba_news() -> None:
    text = "CBA poinformowało o wynikach kontroli w urzędzie."
    document = run_anti_corruption_pipeline(text, (organization_span(text, "CBA"),))

    assert fact_records(document) == ()


def test_anti_corruption_stage_does_not_emit_investigation_for_published_control_results() -> None:
    text = "NIK opublikowała wyniki kontroli spółki Wodkan."
    document = run_anti_corruption_pipeline(
        text,
        (
            organization_span(text, "NIK"),
            organization_span(text, "Wodkan"),
        ),
    )

    assert fact_records(document) == ()
