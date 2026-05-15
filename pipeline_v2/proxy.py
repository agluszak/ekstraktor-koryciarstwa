from __future__ import annotations

from pipeline_v2.candidates import EntityCandidate, PersonalTieFactCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, FactCandidateId, ProducerId
from pipeline_v2.types import EntityKind, GroundingKind, ReferenceKind, positive_signal


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
                    id=EntityCandidateId(f"proxy-{len(document.store.entity_candidates)}"),
                    kind=EntityKind.PERSON,
                    mention_ids=(),
                    reference_ids=(reference.id,),
                    canonical_hint=canonical_hint,
                    grounding=GroundingKind.PROXY,
                    source=self.producer_id,
                )
            )
            document.store.add_fact_candidate(
                PersonalTieFactCandidate(
                    id=FactCandidateId(f"fact-{len(document.store.fact_candidates)}"),
                    subject_entity_id=proxy_id,
                    object_entity_id=anchor.id,
                    evidence_ids=(reference.evidence_id,),
                    source=self.producer_id,
                    relationship_detail=reference.relationship_detail,
                    signals=(
                        positive_signal("proxy_family_entity"),
                        positive_signal(
                            "relationship_detail",
                            details=reference.relationship_detail.value,
                        ),
                    ),
                )
            )
        return document

    @staticmethod
    def _canonical_hint(relationship: str, anchor: EntityCandidate) -> str:
        anchor_name = anchor.canonical_hint or str(anchor.id)
        return f"{relationship} of {anchor_name}"
