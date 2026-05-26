from __future__ import annotations

from pipeline_v2.anti_corruption import AntiCorruptionCandidateStage
from pipeline_v2.candidates import ArgumentBindingCandidate, EntityFiller
from pipeline_v2.document import ArticleDocument
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.ids import DocumentId, EntityCandidateId
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.party import PartyCandidateStage
from pipeline_v2.roles import RoleCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import EntityKind, EventRole, FactKind, NerLabel
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


def organization_span_at(text: str, name: str, start_index: int) -> NamedEntitySpan:
    offset = text.index(name, start_index)
    return NamedEntitySpan(
        text=name,
        label=NerLabel.ORGANIZATION,
        span=Span(offset, offset + len(name)),
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


def test_anti_corruption_stage_keeps_person_and_party_complainant_candidates() -> None:
    text = "Jan Kowalski z PiS złożył zawiadomienie do CBA w sprawie konkursu."
    document = run_anti_corruption_pipeline(
        text,
        (
            person_span(text, "Jan Kowalski"),
            organization_span(text, "CBA"),
        ),
    )

    referral_event = next(
        event
        for event in document.store.event_candidates.values()
        if event.kind is FactKind.ANTI_CORRUPTION_REFERRAL
    )
    complainant_bindings = tuple(
        binding
        for binding in document.store.argument_bindings_for_event(referral_event.id)
        if binding.role is EventRole.COMPLAINANT
    )
    complainant_hints: set[str | None] = set()
    for binding in complainant_bindings:
        match binding.filler:
            case EntityFiller(entity_id=entity_id):
                complainant_hints.add(document.store.entity_candidates[entity_id].canonical_hint)
            case _:
                continue

    assert "Jan Kowalski" in complainant_hints
    assert any(
        hint is not None and "sprawiedliwość" in hint.casefold() for hint in complainant_hints
    )


def test_anti_corruption_stage_keeps_competing_target_candidates() -> None:
    text = "Radni PiS złożyli zawiadomienie do CBA w sprawie spółki Wodkan i Jana Nowaka."
    document = run_anti_corruption_pipeline(
        text,
        (
            organization_span(text, "CBA"),
            organization_span(text, "Wodkan"),
            person_span(text, "Jana Nowaka"),
        ),
    )

    referral_event = next(
        event
        for event in document.store.event_candidates.values()
        if event.kind is FactKind.ANTI_CORRUPTION_REFERRAL
    )
    target_hints = {
        document.store.entity_candidates[entity_id].canonical_hint
        for binding in document.store.argument_bindings_for_event(referral_event.id)
        if binding.role is EventRole.TARGET
        for entity_id in _entity_filler_ids(binding)
    }

    assert target_hints == {"Wodkan", "Jana Nowaka"}


def test_anti_corruption_stage_emits_impersonal_referral_to_prosecutor() -> None:
    text = "Sprawę skierowano do prokuratury po kontroli w urzędzie."
    document = run_anti_corruption_pipeline(text)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.ANTI_CORRUPTION_REFERRAL
    assert text_argument(record, "institution") == "prokuratury"
    assert assessment.score >= 0.5


def test_anti_corruption_stage_merges_repeated_referral_restatements() -> None:
    text = (
        "Radni PiS złożyli zawiadomienie do CBA. "
        "Informacja w sprawie złożenia zawiadomienia do CBA dotarła do urzędu."
    )
    first_cba = organization_span(text, "CBA")
    second_cba = organization_span_at(text, "CBA", first_cba.span.end_char)
    document = run_anti_corruption_pipeline(
        text,
        (
            first_cba,
            second_cba,
        ),
    )

    referral_records = [
        record
        for record in fact_records(document)
        if record.kind is FactKind.ANTI_CORRUPTION_REFERRAL
    ]

    assert len(referral_records) == 1
    assert entity_hint_for_role(document, referral_records[0], "institution") == "CBA"
    assert "complainant" in argument_roles(referral_records[0])
    assert document.materialized_fact_alternatives[referral_records[0].id]


def _entity_filler_ids(binding: ArgumentBindingCandidate) -> tuple[EntityCandidateId, ...]:
    match binding.filler:
        case EntityFiller(entity_id=entity_id):
            return (entity_id,)
        case _:
            return ()


def test_anti_corruption_stage_does_not_merge_distinct_referral_contexts() -> None:
    text = (
        "Radni PiS złożyli zawiadomienie do CBA w sprawie zatrudnienia. "
        "Radni PiS złożyli zawiadomienie do CBA w sprawie przetargu."
    )
    first_cba = organization_span(text, "CBA")
    second_cba = organization_span_at(text, "CBA", first_cba.span.end_char)
    document = run_anti_corruption_pipeline(text, (first_cba, second_cba))

    referral_records = tuple(
        record
        for record in fact_records(document)
        if record.kind is FactKind.ANTI_CORRUPTION_REFERRAL
    )
    contexts = {text_argument(record, "context") for record in referral_records}

    assert len(referral_records) == 2
    assert contexts == {"w sprawie zatrudnienia", "w sprawie przetargu"}


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
