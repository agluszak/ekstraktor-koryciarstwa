from __future__ import annotations

from pipeline_v2.document import ArticleDocument
from pipeline_v2.fact_scoring import FactScoringStage
from pipeline_v2.ids import (
    ArgumentBindingCandidateId,
    DocumentId,
    EntityCandidateId,
    EventCandidateId,
)
from pipeline_v2.types import (
    DirectPrepositionalAttachmentSignal,
    EntityKind,
    EventRole,
    ExplicitNonPartyContextSignal,
    FactKind,
    GroundingKind,
    PartyAliasMatchSignal,
)
from tests_v2.materialized import add_entity, add_event, bind_entity, first_fact_record


def test_party_inference_keeps_non_party_context_as_negative_signal() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Wojciech Wilk z PO oraz Krzysztof Staruch, bezpartyjny, rozmawiali.",
        paragraphs=("Wojciech Wilk z PO oraz Krzysztof Staruch, bezpartyjny, rozmawiali.",),
    )
    subject_id = add_entity(
        document,
        entity_id=EntityCandidateId("staruch"),
        kind=EntityKind.PERSON,
        canonical_hint="Krzysztof Staruch",
    )
    party_id = add_entity(
        document,
        entity_id=EntityCandidateId("po"),
        kind=EntityKind.POLITICAL_PARTY,
        canonical_hint="Platforma Obywatelska",
        grounding=GroundingKind.OBSERVED,
    )
    add_event(
        document,
        event_id=EventCandidateId("event-1"),
        kind=FactKind.PARTY_AFFILIATION,
        signals=(
            PartyAliasMatchSignal(),
            DirectPrepositionalAttachmentSignal(),
            ExplicitNonPartyContextSignal(),
        ),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("binding-subject"),
        event_id=EventCandidateId("event-1"),
        role=EventRole.SUBJECT,
        entity_id=subject_id,
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("binding-object"),
        event_id=EventCandidateId("event-1"),
        role=EventRole.OBJECT,
        entity_id=party_id,
    )

    FactScoringStage().run(document)

    record = first_fact_record(document)
    assessment = document.fact_assessments[0].assessment

    assert record.kind is FactKind.PARTY_AFFILIATION
    assert assessment.score < 0.5
    assert ExplicitNonPartyContextSignal() in assessment.negative_signals
