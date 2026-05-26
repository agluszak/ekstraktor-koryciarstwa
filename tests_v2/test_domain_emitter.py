from __future__ import annotations

from pipeline_v2.candidates import EntityFiller, TextFiller
from pipeline_v2.document import ArticleDocument
from pipeline_v2.domain_emitter import DomainEventEmitter
from pipeline_v2.ids import DocumentId, EntityCandidateId, EvidenceId, ProducerId
from pipeline_v2.types import EventRole, FactKind, LocalInstitutionSignal, LocalTargetSignal


def test_domain_event_emitter_preserves_event_and_role_binding_hypotheses() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="",
        paragraphs=(),
    )
    emitter = DomainEventEmitter(document=document, producer_id=ProducerId("test-domain"))

    event = emitter.event(
        kind=FactKind.ANTI_CORRUPTION_REFERRAL,
        trigger_evidence_id=EvidenceId("evidence-trigger"),
        evidence_ids=(EvidenceId("evidence-trigger"),),
        signals=(LocalInstitutionSignal(),),
    )
    emitter.bind_entity(
        event=event,
        role=EventRole.TARGET,
        entity_id=EntityCandidateId("entity-target"),
        evidence_ids=(EvidenceId("evidence-target"),),
        signals=(LocalTargetSignal(),),
    )
    emitter.bind_text(
        event=event,
        role=EventRole.INSTITUTION,
        value="CBA",
        evidence_ids=(EvidenceId("evidence-institution"),),
        signals=(LocalInstitutionSignal(),),
    )

    stored_event = document.store.event_candidates[event.id]
    bindings = document.store.argument_bindings_for_event(event.id)

    assert stored_event.kind is FactKind.ANTI_CORRUPTION_REFERRAL
    assert stored_event.source == ProducerId("test-domain")
    assert stored_event.signals == (LocalInstitutionSignal(),)
    assert len(bindings) == 2
    assert any(
        binding.role is EventRole.TARGET
        and binding.filler == EntityFiller(EntityCandidateId("entity-target"))
        and binding.signals == (LocalTargetSignal(),)
        for binding in bindings
    )
    assert any(
        binding.role is EventRole.INSTITUTION
        and binding.filler == TextFiller("CBA")
        and binding.signals == (LocalInstitutionSignal(),)
        for binding in bindings
    )
