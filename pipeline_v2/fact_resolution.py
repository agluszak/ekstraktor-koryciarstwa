from __future__ import annotations

from collections import defaultdict

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
from pipeline_v2.types import DuplicateFactSignal, FactArgumentRole, FactKind, ResolutionRelation


class FactResolutionStage:
    producer_id = ProducerId("fact_resolution_stage_v2")
    _governance_kinds = frozenset(
        {
            FactKind.GOVERNANCE_APPOINTMENT,
            FactKind.GOVERNANCE_DISMISSAL,
        }
    )

    def name(self) -> str:
        return "fact_resolution_stage_v2"

    def run(self, document: ArticleDocument) -> ArticleDocument:
        self._same_as_neighbors = self._build_same_as_neighbors(document)
        self._resolved_entity_ids: dict[str, str] = {}
        scorer = FactResolutionScorer()
        by_signature: dict[str, list[FactCandidateRecord]] = defaultdict(list)
        for candidate in document.store.fact_candidates.values():
            record = candidate.to_fact_record()
            for signature in self._signatures(record):
                by_signature[signature].append(record)

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

    def _build_same_as_neighbors(self, document: ArticleDocument) -> dict[str, set[str]]:
        neighbors: dict[str, set[str]] = defaultdict(set)
        for claim in document.store.resolution_claims.values():
            if claim.relation is not ResolutionRelation.SAME_AS:
                continue
            left = str(claim.left_entity_id)
            right = str(claim.right_entity_id)
            neighbors[left].add(right)
            neighbors[right].add(left)
        return neighbors

    def _resolved_entity_id(self, entity_id: str) -> str:
        cached = self._resolved_entity_ids.get(entity_id)
        if cached is not None:
            return cached
        component = {entity_id}
        queue = [entity_id]
        while queue:
            current = queue.pop()
            for neighbor in self._same_as_neighbors.get(current, set()):
                if neighbor in component:
                    continue
                component.add(neighbor)
                queue.append(neighbor)
        canonical = min(component)
        for member in component:
            self._resolved_entity_ids[member] = canonical
        return canonical

    def _signatures(self, record: FactCandidateRecord) -> tuple[str, ...]:
        signatures = [
            self._signature(
                record,
                relax_governance_role=False,
                ignore_tie_context=False,
            )
        ]
        if self._can_relax_governance_role(record):
            relaxed = self._signature(
                record,
                relax_governance_role=True,
                ignore_tie_context=False,
            )
            if relaxed not in signatures:
                signatures.append(relaxed)
        if self._can_relax_tie_context(record):
            relaxed = self._signature(
                record,
                relax_governance_role=False,
                ignore_tie_context=True,
            )
            if relaxed not in signatures:
                signatures.append(relaxed)
        return tuple(signatures)

    def _signature(
        self,
        record: FactCandidateRecord,
        *,
        relax_governance_role: bool,
        ignore_tie_context: bool,
    ) -> str:
        argument_parts: list[tuple[str, str, str]] = []
        for argument in record.arguments:
            match argument:
                case EntityFactArgument(role=role, entity_id=entity_id):
                    if (
                        relax_governance_role
                        and record.kind in self._governance_kinds
                        and role is FactArgumentRole.ROLE
                    ):
                        continue
                    argument_parts.append(
                        (
                            role.value,
                            "entity",
                            self._resolved_entity_id(str(entity_id)),
                        )
                    )
                case TextFactArgument(role=role, value=value):
                    if (
                        ignore_tie_context
                        and record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
                        and role is FactArgumentRole.CONTEXT
                    ):
                        continue
                    argument_parts.append((role.value, "text", value.casefold()))
        return repr((record.kind.value, tuple(sorted(argument_parts))))

    def _can_relax_governance_role(self, record: FactCandidateRecord) -> bool:
        if record.kind not in self._governance_kinds:
            return False
        for argument in record.arguments:
            match argument:
                case EntityFactArgument(role=FactArgumentRole.ORGANIZATION):
                    return True
        return False

    def _can_relax_tie_context(self, record: FactCandidateRecord) -> bool:
        if record.kind is not FactKind.PERSONAL_OR_POLITICAL_TIE:
            return False
        for argument in record.arguments:
            match argument:
                case TextFactArgument(role=FactArgumentRole.RELATIONSHIP_DETAIL):
                    return True
        return False
