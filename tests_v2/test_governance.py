from __future__ import annotations

from pipeline_v2.document import ArticleDocument
from pipeline_v2.fact_scoring import FactScoringStage
from pipeline_v2.governance import GovernanceCandidateStage
from pipeline_v2.ids import DocumentId
from pipeline_v2.morphology import MorfeuszMorphologyStage
from pipeline_v2.ner import NamedEntityCandidateStage
from pipeline_v2.nlp import Morfeusz2MorphologyAdapter, NamedEntitySpan, Span
from pipeline_v2.roles import RoleCandidateStage
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import FactKind, NerLabel


class StaticEntityProvider:
    def __init__(self, entities: tuple[NamedEntitySpan, ...]) -> None:
        self.entities = entities

    def find_entities(self, text: str) -> tuple[NamedEntitySpan, ...]:
        _ = text
        return self.entities


def run_governance_stage(
    text: str,
    entities: tuple[NamedEntitySpan, ...],
    paragraphs: tuple[str, ...] | None = None,
) -> ArticleDocument:
    actual_paragraphs = paragraphs or (text,)
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=text,
        paragraphs=actual_paragraphs,
    )
    morphology = Morfeusz2MorphologyAdapter()
    ParagraphSentenceSegmenter().run(document)
    MorfeuszMorphologyStage(morphology).run(document)
    NamedEntityCandidateStage(
        provider=StaticEntityProvider(entities),
        morphology=morphology,
    ).run(document)
    RoleCandidateStage(morphology).run(document)
    GovernanceCandidateStage().run(document)
    return document


def test_governance_stage_emits_appointment_candidate_with_sentence_local_entities() -> None:
    text = "Jan Kowalski został powołany do zarządu spółki Wodkan."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + 12),
            ),
            NamedEntitySpan(
                text="Wodkan",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Wodkan"), text.index("Wodkan") + 6),
            ),
        ),
    )

    record = next(iter(document.store.fact_candidates.values())).to_fact_record()

    assert record.kind is FactKind.GOVERNANCE_APPOINTMENT
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "person", "entity_id": "entity-0"},
        {"role": "organization", "entity_id": "entity-1"},
        {"role": "role", "entity_id": "entity-2"},
    )
    assert tuple(signal.name for signal in record.signals) == (
        "appointment_lemma",
        "sentence_local_person",
        "sentence_local_organization",
        "sentence_local_role",
    )


def test_governance_stage_emits_dismissal_candidate_and_fact_score() -> None:
    text = "Anna Nowak została odwołana z rady nadzorczej spółki Komunalnik."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Anna Nowak",
                label=NerLabel.PERSON,
                span=Span(text.index("Anna Nowak"), text.index("Anna Nowak") + 10),
            ),
            NamedEntitySpan(
                text="Komunalnik",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Komunalnik"), text.index("Komunalnik") + 9),
            ),
        ),
    )

    FactScoringStage().run(document)
    record = next(iter(document.store.fact_candidates.values())).to_fact_record()

    assert record.kind is FactKind.GOVERNANCE_DISMISSAL
    assert document.fact_assessments[0].assessment.score >= 0.6


def test_governance_stage_does_not_emit_candidate_without_person_entity() -> None:
    text = "Zarząd spółki Wodkan został powołany w maju."
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Wodkan",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Wodkan"), text.index("Wodkan") + 6),
            ),
        ),
    )

    assert tuple(document.store.fact_candidates.values()) == ()


def test_governance_stage_uses_adjacent_sentence_context_for_split_appointment() -> None:
    first = "Jan Kowalski jest prezesem spółki Wodkan."
    second = "Został powołany bez konkursu."
    text = f"{first} {second}"
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + 12),
            ),
            NamedEntitySpan(
                text="Wodkan",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Wodkan"), text.index("Wodkan") + 6),
            ),
        ),
    )

    record = next(iter(document.store.fact_candidates.values())).to_fact_record()

    assert record.kind is FactKind.GOVERNANCE_APPOINTMENT
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "person", "entity_id": "entity-0"},
        {"role": "organization", "entity_id": "entity-1"},
        {"role": "role", "entity_id": "entity-2"},
    )
    assert tuple(signal.name for signal in record.signals) == (
        "appointment_lemma",
        "discourse_window_person",
        "discourse_window_organization",
        "discourse_window_role",
    )


def test_governance_stage_does_not_use_previous_paragraph_for_missing_person() -> None:
    first = "Jan Kowalski jest prezesem spółki Wodkan."
    second = "Został powołany bez konkursu."
    text = f"{first}\n{second}"
    document = run_governance_stage(
        text,
        (
            NamedEntitySpan(
                text="Jan Kowalski",
                label=NerLabel.PERSON,
                span=Span(text.index("Jan Kowalski"), text.index("Jan Kowalski") + 12),
            ),
            NamedEntitySpan(
                text="Wodkan",
                label=NerLabel.ORGANIZATION,
                span=Span(text.index("Wodkan"), text.index("Wodkan") + 6),
            ),
        ),
        paragraphs=(first, second),
    )

    assert tuple(document.store.fact_candidates.values()) == ()
