from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from pipeline_v2.candidates import (
    EntityFactArgument,
    FactCandidateRecord,
    FactResolutionClaim,
    FactResolutionProposal,
    TextFactArgument,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import EntityCandidateId, FactCandidateId, ProducerId
from pipeline_v2.scoring import FactResolutionScorer
from pipeline_v2.types import (
    DuplicateFactSignal,
    FactArgumentRole,
    FactKind,
    FactResolutionStrategy,
    GroundingKind,
    PseudonymousSourceSignal,
    ResolutionRelation,
)

type SignatureArgument = tuple[FactArgumentRole, EntityCandidateId | str]


@dataclass(frozen=True, slots=True)
class FactSignature:
    kind: FactKind
    strategy: FactResolutionStrategy
    arguments: tuple[SignatureArgument, ...]


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
        self._resolved_entity_ids: dict[EntityCandidateId, EntityCandidateId] = {}
        scorer = FactResolutionScorer()
        by_signature: dict[FactSignature, list[FactCandidateRecord]] = defaultdict(list)
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
                if self._has_existing_pair(existing_pairs, first.id, duplicate.id):
                    continue
                self._add_claim(
                    document=document,
                    scorer=scorer,
                    left=first,
                    right=duplicate,
                    signature=signature,
                    existing_pairs=existing_pairs,
                )
        for left, right, signature in self._proxy_named_tie_pairs(document):
            if self._has_existing_pair(existing_pairs, left.id, right.id):
                continue
            self._add_claim(
                document=document,
                scorer=scorer,
                left=left,
                right=right,
                signature=signature,
                existing_pairs=existing_pairs,
            )
        return document

    def _add_claim(
        self,
        *,
        document: ArticleDocument,
        scorer: FactResolutionScorer,
        left: FactCandidateRecord,
        right: FactCandidateRecord,
        signature: FactSignature,
        existing_pairs: set[frozenset[FactCandidateId]],
    ) -> None:
        proposal = FactResolutionProposal(
            left_fact_id=left.id,
            right_fact_id=right.id,
            relation=ResolutionRelation.SAME_FACT,
            evidence_ids=tuple(dict.fromkeys([*left.evidence_ids, *right.evidence_ids])),
            retrieval_signals=(
                DuplicateFactSignal(strategy=signature.strategy, fact_kind=signature.kind),
            ),
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
        existing_pairs.add(frozenset((left.id, right.id)))

    @staticmethod
    def _has_existing_pair(
        existing_pairs: set[frozenset[FactCandidateId]],
        left_id: FactCandidateId,
        right_id: FactCandidateId,
    ) -> bool:
        return frozenset((left_id, right_id)) in existing_pairs

    def _build_same_as_neighbors(
        self, document: ArticleDocument
    ) -> dict[EntityCandidateId, set[EntityCandidateId]]:
        neighbors: dict[EntityCandidateId, set[EntityCandidateId]] = defaultdict(set)
        for claim in document.store.resolution_claims.values():
            if claim.relation is not ResolutionRelation.SAME_AS:
                continue
            left = claim.left_entity_id
            right = claim.right_entity_id
            neighbors[left].add(right)
            neighbors[right].add(left)
        return neighbors

    def _resolved_entity_id(self, entity_id: EntityCandidateId) -> EntityCandidateId:
        cached = self._resolved_entity_ids.get(entity_id)
        if cached is not None:
            return cached
        component: set[EntityCandidateId] = {entity_id}
        queue = [entity_id]
        while queue:
            current = queue.pop()
            for neighbor in self._same_as_neighbors.get(current, set()):
                if neighbor in component:
                    continue
                component.add(neighbor)
                queue.append(neighbor)
        canonical = EntityCandidateId(min(str(member) for member in component))
        for member in component:
            self._resolved_entity_ids[member] = canonical
        return canonical

    def _signatures(self, record: FactCandidateRecord) -> tuple[FactSignature, ...]:
        signatures = [
            self._signature(
                record,
                strategy=FactResolutionStrategy.EXACT_ARGUMENTS,
                relax_governance_role=False,
                ignore_tie_context=False,
            )
        ]
        if self._can_relax_governance_role(record):
            relaxed = self._signature(
                record,
                strategy=FactResolutionStrategy.GOVERNANCE_ROLE_RELAXED,
                relax_governance_role=True,
                ignore_tie_context=False,
            )
            if relaxed not in signatures:
                signatures.append(relaxed)
        if self._can_relax_tie_context(record):
            relaxed = self._signature(
                record,
                strategy=FactResolutionStrategy.TIE_CONTEXT_RELAXED,
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
        strategy: FactResolutionStrategy,
    ) -> FactSignature:
        argument_parts: list[SignatureArgument] = []
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
                            role,
                            self._resolved_entity_id(entity_id),
                        )
                    )
                case TextFactArgument(role=role, value=value):
                    if (
                        ignore_tie_context
                        and record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
                        and role is FactArgumentRole.CONTEXT
                    ):
                        continue
                    argument_parts.append((role, value.casefold()))
        return FactSignature(
            kind=record.kind,
            strategy=strategy,
            arguments=tuple(sorted(argument_parts, key=lambda item: (item[0].value, str(item[1])))),
        )

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

    def _proxy_named_tie_pairs(
        self,
        document: ArticleDocument,
    ) -> tuple[tuple[FactCandidateRecord, FactCandidateRecord, FactSignature], ...]:
        tie_records = [
            candidate.to_fact_record()
            for candidate in document.store.fact_candidates.values()
            if candidate.to_fact_record().kind is FactKind.PERSONAL_OR_POLITICAL_TIE
        ]
        pairs: list[tuple[FactCandidateRecord, FactCandidateRecord, FactSignature]] = []
        for index, left in enumerate(tie_records):
            left_subject = self._entity_argument_id(left, FactArgumentRole.SUBJECT)
            left_object = self._entity_argument_id(left, FactArgumentRole.OBJECT)
            left_detail = self._text_argument_value(left, FactArgumentRole.RELATIONSHIP_DETAIL)
            if left_subject is None or left_object is None or left_detail is None:
                continue
            if (
                left_subject not in document.store.entity_candidates
                or left_object not in document.store.entity_candidates
            ):
                continue
            left_grounding = document.store.entity_candidates[left_subject].grounding
            if left_grounding is not GroundingKind.PROXY:
                continue
            for right in tie_records[index + 1 :]:
                right_subject = self._entity_argument_id(right, FactArgumentRole.SUBJECT)
                right_object = self._entity_argument_id(right, FactArgumentRole.OBJECT)
                right_detail = self._text_argument_value(
                    right,
                    FactArgumentRole.RELATIONSHIP_DETAIL,
                )
                if right_subject is None or right_object is None or right_detail is None:
                    continue
                if (
                    right_subject not in document.store.entity_candidates
                    or right_object not in document.store.entity_candidates
                ):
                    continue
                right_grounding = document.store.entity_candidates[right_subject].grounding
                if right_grounding is GroundingKind.PROXY:
                    continue
                if self._resolved_entity_id(left_object) != self._resolved_entity_id(right_object):
                    continue
                if left_detail.casefold() != right_detail.casefold():
                    continue
                if self._has_pseudonymous_signal(right):
                    continue
                if self._fact_paragraph_distance(document, left, right) > 1:
                    continue
                signature = FactSignature(
                    kind=FactKind.PERSONAL_OR_POLITICAL_TIE,
                    strategy=FactResolutionStrategy.PROXY_NAMED_TIE,
                    arguments=(
                        (
                            FactArgumentRole.OBJECT,
                            self._resolved_entity_id(left_object),
                        ),
                        (
                            FactArgumentRole.RELATIONSHIP_DETAIL,
                            left_detail.casefold(),
                        ),
                    ),
                )
                pairs.append((left, right, signature))
        return tuple(pairs)

    def _entity_argument_id(
        self,
        record: FactCandidateRecord,
        role: FactArgumentRole,
    ):
        for argument in record.arguments:
            match argument:
                case EntityFactArgument(role=arg_role, entity_id=entity_id) if arg_role is role:
                    return entity_id
        return None

    def _text_argument_value(
        self,
        record: FactCandidateRecord,
        role: FactArgumentRole,
    ) -> str | None:
        for argument in record.arguments:
            match argument:
                case TextFactArgument(role=arg_role, value=value) if arg_role is role:
                    return value
        return None

    @staticmethod
    def _has_pseudonymous_signal(record: FactCandidateRecord) -> bool:
        for signal in record.signals:
            match signal:
                case PseudonymousSourceSignal():
                    return True
        return False

    def _fact_paragraph_distance(
        self,
        document: ArticleDocument,
        left: FactCandidateRecord,
        right: FactCandidateRecord,
    ) -> int:
        left_paragraphs = [
            paragraph_index
            for evidence_id in left.evidence_ids
            if evidence_id in document.store.evidence
            and (paragraph_index := document.store.evidence[evidence_id].paragraph_index)
            is not None
        ]
        right_paragraphs = [
            paragraph_index
            for evidence_id in right.evidence_ids
            if evidence_id in document.store.evidence
            and (paragraph_index := document.store.evidence[evidence_id].paragraph_index)
            is not None
        ]
        if not left_paragraphs or not right_paragraphs:
            return 999
        return min(
            abs(left_paragraph - right_paragraph)
            for left_paragraph in left_paragraphs
            for right_paragraph in right_paragraphs
        )
