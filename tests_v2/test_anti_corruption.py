from __future__ import annotations

from pipeline_v2.anti_corruption import AntiCorruptionCandidateStage
from pipeline_v2.document import ArticleDocument
from pipeline_v2.fact_scoring import FactScoringStage
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.ids import DocumentId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.party import PartyCandidateStage
from pipeline_v2.roles import RoleCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import EntityKind, FactKind, NerLabel


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

    records = tuple(
        candidate.to_fact_record() for candidate in document.store.fact_candidates.values()
    )
    referral_record = next(
        record for record in records if record.kind is FactKind.ANTI_CORRUPTION_REFERRAL
    )
    referral_assessment = next(
        assessment
        for assessment in document.fact_assessments
        if document.store.fact_candidates[assessment.fact_candidate_id].to_fact_record().kind
        is FactKind.ANTI_CORRUPTION_REFERRAL
    )
    party_entity = next(
        entity
        for entity in document.store.entity_candidates.values()
        if entity.kind is EntityKind.POLITICAL_PARTY
    )

    assert tuple(argument.to_json() for argument in referral_record.arguments) == (
        {"role": "complainant", "entity_id": str(party_entity.id)},
        {"role": "target", "entity_id": "entity-1"},
        {"role": "institution", "entity_id": "entity-0"},
        {"role": "context", "value": "w sprawie zatrudnienia Jana Nowaka"},
    )
    assert referral_assessment.assessment.score >= 0.8
    governance_records = tuple(
        record
        for record in records
        if record.kind in {FactKind.GOVERNANCE_APPOINTMENT, FactKind.GOVERNANCE_DISMISSAL}
    )
    assert all(
        argument.to_json() != {"role": "organization", "entity_id": str(party_entity.id)}
        for record in governance_records
        for argument in record.arguments
    )


def test_anti_corruption_stage_emits_impersonal_referral_to_prosecutor() -> None:
    text = "Sprawę skierowano do prokuratury po kontroli w urzędzie."
    document = run_anti_corruption_pipeline(text)

    record = next(iter(document.store.fact_candidates.values())).to_fact_record()
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.ANTI_CORRUPTION_REFERRAL
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "institution", "value": "prokuratury"},
    )
    assert assessment.score >= 0.7


def test_anti_corruption_stage_emits_investigation_for_nik_control() -> None:
    text = "NIK wszczęła kontrolę w spółce Wodkan."
    document = run_anti_corruption_pipeline(
        text,
        (
            organization_span(text, "NIK"),
            organization_span(text, "Wodkan"),
        ),
    )

    record = next(iter(document.store.fact_candidates.values())).to_fact_record()
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.ANTI_CORRUPTION_INVESTIGATION
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "target", "entity_id": "entity-1"},
        {"role": "institution", "entity_id": "entity-0"},
    )
    assert assessment.score >= 0.7


def test_anti_corruption_stage_emits_investigation_with_text_institution_fallback() -> None:
    text = "Prokuratura wszczęła śledztwo w sprawie Jana Nowaka."
    document = run_anti_corruption_pipeline(text, (person_span(text, "Jana Nowaka"),))

    record = next(iter(document.store.fact_candidates.values())).to_fact_record()

    assert record.kind is FactKind.ANTI_CORRUPTION_INVESTIGATION
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "target", "entity_id": "entity-0"},
        {"role": "institution", "value": "Prokuratura"},
        {"role": "context", "value": "w sprawie Jana Nowaka"},
    )


def test_anti_corruption_stage_does_not_emit_referral_for_ordinary_cba_news() -> None:
    text = "CBA poinformowało o wynikach kontroli w urzędzie."
    document = run_anti_corruption_pipeline(text, (organization_span(text, "CBA"),))

    assert tuple(document.store.fact_candidates.values()) == ()


def test_anti_corruption_stage_does_not_emit_investigation_for_published_control_results() -> None:
    text = "NIK opublikowała wyniki kontroli spółki Wodkan."
    document = run_anti_corruption_pipeline(
        text,
        (
            organization_span(text, "NIK"),
            organization_span(text, "Wodkan"),
        ),
    )

    assert tuple(document.store.fact_candidates.values()) == ()
