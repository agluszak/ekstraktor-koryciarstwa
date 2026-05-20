from __future__ import annotations

from pipeline_v2.candidates import EntityResolutionClaim, ReferenceResolutionClaim
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import ProducerId
from pipeline_v2.orchestrator import V2Orchestrator
from pipeline_v2.types import ResolutionRelation


class ResolutionScoringStage:
    producer_id = ProducerId("resolution_scoring_stage_v2")

    def name(self) -> str:
        return "resolution_scoring_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        result = V2Orchestrator(document.store).assess(
            entities=tuple(document.store.entity_candidates.values()),
            reference_resolutions=tuple(document.reference_resolution_proposals),
        )
        seen_pairs: set[tuple[str, str]] = set()
        for entity_assessment in result.entity_resolution_assessments:
            left_id = str(entity_assessment.proposal.left_entity_id)
            right_id = str(entity_assessment.proposal.right_entity_id)
            pair = (left_id, right_id) if left_id <= right_id else (right_id, left_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            document.store.add_resolution_claim(
                EntityResolutionClaim(
                    id=document.store.next_resolution_claim_id(),
                    left_entity_id=entity_assessment.proposal.left_entity_id,
                    right_entity_id=entity_assessment.proposal.right_entity_id,
                    relation=ResolutionRelation.SAME_AS,
                    evidence_ids=entity_assessment.proposal.evidence_ids,
                    assessment=entity_assessment.assessment,
                    source=self.producer_id,
                )
            )
        for reference_assessment in result.reference_resolution_assessments:
            document.store.add_reference_resolution_claim(
                ReferenceResolutionClaim(
                    id=document.store.next_reference_resolution_claim_id(),
                    reference_id=reference_assessment.proposal.reference_id,
                    candidate_entity_id=reference_assessment.proposal.candidate_entity_id,
                    relation=ResolutionRelation.REFERENT_OF,
                    evidence_ids=reference_assessment.proposal.evidence_ids,
                    assessment=reference_assessment.assessment,
                    source=self.producer_id,
                )
            )
        return document
