from __future__ import annotations

from pipeline_v2.candidates import (
    EntityFactArgument,
    FactCandidateRecord,
    FactResolutionClaim,
    FactResolutionProposal,
    TextFactArgument,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import ProducerId
from pipeline_v2.scoring import FactResolutionScorer
from pipeline_v2.types import DuplicateFactSignal, ResolutionRelation


class FactResolutionStage:
    producer_id = ProducerId("fact_resolution_stage_v2")

    def name(self) -> str:
        return "fact_resolution_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        scorer = FactResolutionScorer()
        by_signature: dict[str, list[FactCandidateRecord]] = {}
        for candidate in document.store.fact_candidates.values():
            record = candidate.to_fact_record()
            by_signature.setdefault(self._signature(record), []).append(record)

        existing_pairs = {
            frozenset((claim.left_fact_id, claim.right_fact_id))
            for claim in document.store.fact_resolution_claims.values()
        }
        for signature, records in by_signature.items():
            if len(records) < 2:
                continue
            first = records[0]
            for duplicate in records[1:]:
                pair = frozenset((first.id, duplicate.id))
                if pair in existing_pairs:
                    continue
                proposal = FactResolutionProposal(
                    left_fact_id=first.id,
                    right_fact_id=duplicate.id,
                    relation=ResolutionRelation.SAME_FACT,
                    evidence_ids=tuple(
                        dict.fromkeys([*first.evidence_ids, *duplicate.evidence_ids])
                    ),
                    retrieval_signals=(DuplicateFactSignal(signature=signature),),
                )
                assessment = scorer.score(proposal)
                document.store.add_fact_resolution_claim(
                    FactResolutionClaim(
                        id=document.store.next_fact_resolution_claim_id(),
                        left_fact_id=proposal.left_fact_id,
                        right_fact_id=proposal.right_fact_id,
                        relation=proposal.relation,
                        evidence_ids=proposal.evidence_ids,
                        assessment=assessment,
                        source=self.producer_id,
                    )
                )
        return document

    def _signature(self, record: FactCandidateRecord) -> str:
        argument_parts = []
        for argument in record.arguments:
            match argument:
                case EntityFactArgument(role=role, entity_id=entity_id):
                    argument_parts.append((role.value, "entity", str(entity_id)))
                case TextFactArgument(role=role, value=value):
                    argument_parts.append((role.value, "text", value.casefold()))
        return repr((record.kind.value, tuple(sorted(argument_parts))))
