from __future__ import annotations

from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import (
    ArgumentBindingCandidateId,
    DocumentId,
    EntityCandidateId,
    EventCandidateId,
)
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.types import (
    DirectPrepositionalAttachmentSignal,
    EntityKind,
    EventRole,
    ExplicitNonPartyContextSignal,
    FactKind,
    GroundingKind,
    PartyAliasMatchSignal,
)
from tests_v2.materialized import add_entity, add_event, bind_entity, fact_records


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
        kind=FactKind.PARTY_MEMBERSHIP,
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

    ProbabilisticInferenceStage().run(document)

    assert fact_records(document) == ()
    assert any(
        event.kind is FactKind.PARTY_MEMBERSHIP and ExplicitNonPartyContextSignal() in event.signals
        for event in document.store.event_candidates.values()
    )
