from __future__ import annotations

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    EntityCandidate,
    EntityFiller,
    EventCandidate,
    TextFiller,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import ProducerId
from pipeline_v2.types import (
    EntityKind,
    EventRole,
    FactKind,
    GroundingKind,
    ProxyFamilyEntitySignal,
    ReferenceKind,
    RelationshipDetailSignal,
)


class FamilyProxyCandidateStage:
    producer_id = ProducerId("family_proxy_candidate_stage_v2")

    def name(self) -> str:
        return "family_proxy_candidate_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        for proposal in document.reference_resolution_proposals:
            reference = document.store.references[proposal.reference_id]
            if reference.kind != ReferenceKind.PROXY_FAMILY_PHRASE:
                continue
            if reference.relationship_detail is None:
                continue
            anchor = document.store.entity_candidates[proposal.candidate_entity_id]
            canonical_hint = self._canonical_hint(reference.relationship_detail.value, anchor)
            proxy_id = document.store.add_entity_candidate(
                EntityCandidate(
                    id=document.store.next_proxy_candidate_id(),
                    kind=EntityKind.PERSON,
                    mention_ids=(),
                    reference_ids=(reference.id,),
                    canonical_hint=canonical_hint,
                    grounding=GroundingKind.PROXY,
                    source=self.producer_id,
                )
            )
            event = EventCandidate(
                id=document.store.next_event_candidate_id(),
                kind=FactKind.KINSHIP_TIE,
                trigger_evidence_id=reference.evidence_id,
                evidence_ids=(reference.evidence_id,),
                source=self.producer_id,
                signals=(
                    ProxyFamilyEntitySignal(),
                    RelationshipDetailSignal(detail=reference.relationship_detail),
                ),
            )
            document.store.add_event_candidate(event)
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=EventRole.SUBJECT,
                    filler=EntityFiller(proxy_id),
                    evidence_ids=(reference.evidence_id,),
                )
            )
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=EventRole.OBJECT,
                    filler=EntityFiller(anchor.id),
                    evidence_ids=(reference.evidence_id,),
                )
            )
            document.store.add_argument_binding(
                ArgumentBindingCandidate(
                    id=document.store.next_argument_binding_candidate_id(),
                    event_id=event.id,
                    role=EventRole.RELATIONSHIP_DETAIL,
                    filler=TextFiller(reference.relationship_detail.value),
                    evidence_ids=(reference.evidence_id,),
                )
            )
        return document

    @staticmethod
    def _canonical_hint(relationship: str, anchor: EntityCandidate) -> str:
        anchor_name = anchor.canonical_hint or str(anchor.id)
        return f"{relationship} of {anchor_name}"
