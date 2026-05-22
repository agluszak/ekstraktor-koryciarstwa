from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import (
    Assessment,
    EntityCandidate,
    EntityContextClaim,
    EntityContextProposal,
    EntityFiller,
    EntityResolutionClaim,
    EntityResolutionProposal,
    FactResolutionClaim,
    FactResolutionProposal,
    ReferenceResolutionClaim,
    ReferenceResolutionProposal,
    TextFiller,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import (
    EntityCandidateId,
    EventCandidateId,
    EvidenceId,
    FactCandidateId,
    InferenceFactorId,
    InferenceStateId,
    InferenceVariableId,
    MentionId,
    ProducerId,
    ScorerId,
)
from pipeline_v2.inference.entity_context_policy import (
    DEFAULT_ENTITY_CONTEXT_ROLE_POLICY,
    EntityContextRolePolicy,
)
from pipeline_v2.inference.event_schema import schema_for
from pipeline_v2.inference.factor_builders import (
    FALSE_STATE,
    TRUE_STATE,
    UNKNOWN_STATE,
    BuiltFactInferenceGraph,
    RoleFillerState,
)
from pipeline_v2.inference.graph_spec import (
    InferenceFactor,
    InferenceFactorKind,
    InferenceGraphSpec,
    InferenceResult,
    InferenceState,
    InferenceVariable,
    InferenceVariableKind,
)
from pipeline_v2.producers import EvidenceSignalProducer
from pipeline_v2.retrieval import EntityCandidateRetriever
from pipeline_v2.scoring import (
    EntityContextScorer,
    EntityResolutionScorer,
    ReferenceResolutionScorer,
)
from pipeline_v2.types import (
    DuplicateFactSignal,
    EntityKind,
    EntityTag,
    EventRole,
    FactArgumentRole,
    FactKind,
    FactResolutionStrategy,
    GroundingKind,
    MentionKind,
    RelationshipDetail,
    ResolutionRelation,
    SemanticEvidenceSimilaritySignal,
    Signal,
    SignalPolarity,
)


@dataclass(frozen=True, slots=True)
class SameEventProposal:
    left_event_id: EventCandidateId
    right_event_id: EventCandidateId
    strategy: FactResolutionStrategy
    fact_proposal: FactResolutionProposal
    linked_entity_pairs: tuple[tuple[EntityCandidateId, EntityCandidateId], ...] = ()


@dataclass(frozen=True, slots=True)
class BuiltResolutionInferenceGraph:
    spec: InferenceGraphSpec
    entity_proposal_by_variable_id: dict[InferenceVariableId, EntityResolutionProposal]
    reference_state_proposals_by_variable_id: dict[
        InferenceVariableId, dict[InferenceStateId, ReferenceResolutionProposal]
    ]
    same_event_proposal_by_variable_id: dict[InferenceVariableId, SameEventProposal]
    entity_context_proposal_by_variable_id: dict[InferenceVariableId, EntityContextProposal]


@dataclass(frozen=True, slots=True)
class _EventBindingView:
    kind: FactKind
    entity_fillers: dict[FactArgumentRole, frozenset[EntityCandidateId]]
    text_fillers: dict[FactArgumentRole, frozenset[str]]
    entity_groundings: dict[FactArgumentRole, tuple[GroundingKind, ...]]


class ResolutionInferenceGraphBuilder:
    producer_id = ProducerId("probabilistic_inference_stage_v2")
    semantic_same_entity_threshold = 0.9
    semantic_same_event_threshold = 0.82
    semantic_reference_threshold = 0.82

    def __init__(
        self,
        *,
        entity_context_role_policy: EntityContextRolePolicy = (DEFAULT_ENTITY_CONTEXT_ROLE_POLICY),
        entity_context_scorer: EntityContextScorer | None = None,
    ) -> None:
        self.entity_context_role_policy = entity_context_role_policy
        self.entity_context_scorer = entity_context_scorer or EntityContextScorer()

    def build(
        self,
        *,
        document: ArticleDocument,
        fact_graph: BuiltFactInferenceGraph,
    ) -> BuiltResolutionInferenceGraph:
        variables: list[InferenceVariable] = []
        factors: list[InferenceFactor] = []

        entity_proposal_by_variable_id: dict[InferenceVariableId, EntityResolutionProposal] = {}
        same_entity_variable_id_by_pair: dict[
            tuple[EntityCandidateId, EntityCandidateId], InferenceVariableId
        ] = {}
        self._add_entity_resolution_variables(
            document=document,
            variables=variables,
            factors=factors,
            entity_proposal_by_variable_id=entity_proposal_by_variable_id,
            same_entity_variable_id_by_pair=same_entity_variable_id_by_pair,
        )
        self._add_same_entity_role_factors(
            document=document,
            fact_graph=fact_graph,
            factors=factors,
            same_entity_variable_id_by_pair=same_entity_variable_id_by_pair,
        )

        reference_state_proposals_by_variable_id: dict[
            InferenceVariableId, dict[InferenceStateId, ReferenceResolutionProposal]
        ] = {}
        reference_variable_id_by_reference_id: dict[MentionId, InferenceVariableId] = {}
        self._add_reference_resolution_variables(
            document=document,
            variables=variables,
            factors=factors,
            reference_state_proposals_by_variable_id=reference_state_proposals_by_variable_id,
            reference_variable_id_by_reference_id=reference_variable_id_by_reference_id,
        )
        self._add_reference_role_factors(
            document=document,
            fact_graph=fact_graph,
            factors=factors,
            reference_variable_id_by_reference_id=reference_variable_id_by_reference_id,
            reference_state_proposals_by_variable_id=reference_state_proposals_by_variable_id,
        )

        self._add_self_tie_entity_factors(
            document=document,
            fact_graph=fact_graph,
            factors=factors,
            same_entity_variable_id_by_pair=same_entity_variable_id_by_pair,
        )

        entity_context_proposal_by_variable_id: dict[
            InferenceVariableId, EntityContextProposal
        ] = {}
        entity_context_variable_id_by_pair: dict[
            tuple[EntityCandidateId, EntityTag], InferenceVariableId
        ] = {}
        self._add_entity_context_variables(
            document=document,
            variables=variables,
            factors=factors,
            entity_context_proposal_by_variable_id=entity_context_proposal_by_variable_id,
            entity_context_variable_id_by_pair=entity_context_variable_id_by_pair,
        )
        self._add_entity_context_role_factors(
            fact_graph=fact_graph,
            factors=factors,
            entity_context_variable_id_by_pair=entity_context_variable_id_by_pair,
        )

        same_event_proposal_by_variable_id: dict[InferenceVariableId, SameEventProposal] = {}
        self._add_same_event_variables(
            document=document,
            fact_graph=fact_graph,
            variables=variables,
            factors=factors,
            same_entity_variable_id_by_pair=same_entity_variable_id_by_pair,
            same_event_proposal_by_variable_id=same_event_proposal_by_variable_id,
        )
        self._add_inverse_child_tie_conflict_factors(
            document=document,
            fact_graph=fact_graph,
            factors=factors,
        )

        return BuiltResolutionInferenceGraph(
            spec=InferenceGraphSpec(variables=tuple(variables), factors=tuple(factors)),
            entity_proposal_by_variable_id=entity_proposal_by_variable_id,
            reference_state_proposals_by_variable_id=reference_state_proposals_by_variable_id,
            same_event_proposal_by_variable_id=same_event_proposal_by_variable_id,
            entity_context_proposal_by_variable_id=entity_context_proposal_by_variable_id,
        )

    def _add_inverse_child_tie_conflict_factors(
        self,
        *,
        document: ArticleDocument,
        fact_graph: BuiltFactInferenceGraph,
        factors: list[InferenceFactor],
    ) -> None:
        event_variable_id_by_event_id = {
            event_id: variable_id
            for variable_id, event_id in fact_graph.index.event_id_by_event_variable_id.items()
        }
        event_views = self._event_views(document)
        tie_event_ids: list[EventCandidateId] = [
            event_id
            for event_id, view in event_views.items()
            if view.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
            and RelationshipDetail.CHILD.value
            in view.text_fillers.get(FactArgumentRole.RELATIONSHIP_DETAIL, frozenset())
        ]
        tie_event_ids.sort(key=lambda event_id: str(event_id))
        for index, left_event_id in enumerate(tie_event_ids):
            left_view = event_views[left_event_id]
            left_subject = left_view.entity_fillers.get(FactArgumentRole.SUBJECT, frozenset())
            left_object = left_view.entity_fillers.get(FactArgumentRole.OBJECT, frozenset())
            if len(left_subject) != 1 or len(left_object) != 1:
                continue
            for right_event_id in tie_event_ids[index + 1 :]:
                right_view = event_views[right_event_id]
                right_subject = right_view.entity_fillers.get(FactArgumentRole.SUBJECT, frozenset())
                right_object = right_view.entity_fillers.get(FactArgumentRole.OBJECT, frozenset())
                if len(right_subject) != 1 or len(right_object) != 1:
                    continue
                if left_subject != right_object or left_object != right_subject:
                    continue
                left_event_variable_id = event_variable_id_by_event_id.get(left_event_id)
                right_event_variable_id = event_variable_id_by_event_id.get(right_event_id)
                if left_event_variable_id is None or right_event_variable_id is None:
                    continue
                factors.append(
                    self._inverse_child_tie_conflict_factor(
                        left_event_id=left_event_id,
                        right_event_id=right_event_id,
                        left_event_variable_id=left_event_variable_id,
                        right_event_variable_id=right_event_variable_id,
                    )
                )

    def _inverse_child_tie_conflict_factor(
        self,
        *,
        left_event_id: EventCandidateId,
        right_event_id: EventCandidateId,
        left_event_variable_id: InferenceVariableId,
        right_event_variable_id: InferenceVariableId,
    ) -> InferenceFactor:
        values: list[float] = []
        for left_event_state in (FALSE_STATE, TRUE_STATE):
            for right_event_state in (FALSE_STATE, TRUE_STATE):
                if left_event_state.id == TRUE_STATE.id and right_event_state.id == TRUE_STATE.id:
                    values.append(0.01)
                elif left_event_state.id == TRUE_STATE.id or right_event_state.id == TRUE_STATE.id:
                    values.append(1.2)
                else:
                    values.append(1.0)
        return InferenceFactor(
            id=InferenceFactorId(f"factor:inverse-child-tie:{left_event_id}:{right_event_id}"),
            kind=InferenceFactorKind.CONSTRAINT,
            variable_ids=(left_event_variable_id, right_event_variable_id),
            potentials=tuple(values),
        )

    def _add_entity_resolution_variables(
        self,
        *,
        document: ArticleDocument,
        variables: list[InferenceVariable],
        factors: list[InferenceFactor],
        entity_proposal_by_variable_id: dict[InferenceVariableId, EntityResolutionProposal],
        same_entity_variable_id_by_pair: dict[
            tuple[EntityCandidateId, EntityCandidateId], InferenceVariableId
        ],
    ) -> None:
        retriever = EntityCandidateRetriever(document.store)
        signal_producer = EvidenceSignalProducer()
        scorer = EntityResolutionScorer(document.store)
        entity_ids_by_evidence_id = self._entity_ids_by_evidence_id(document)
        seen_pairs: set[tuple[EntityCandidateId, EntityCandidateId]] = set()
        for entity in document.store.entity_candidates.values():
            proposals = (
                *retriever.proposals_for_entity(entity),
                *self._semantic_entity_proposals(
                    document=document,
                    entity=entity,
                    entity_ids_by_evidence_id=entity_ids_by_evidence_id,
                ),
            )
            for proposal in proposals:
                enriched = signal_producer.enrich_resolution_proposal(document.store, proposal)
                pair_key = self._entity_pair(enriched.left_entity_id, enriched.right_entity_id)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                variable_id = InferenceVariableId(
                    f"same-entity:{enriched.left_entity_id}:{enriched.right_entity_id}"
                )
                score = scorer.score(enriched).score
                variables.append(
                    InferenceVariable(
                        id=variable_id,
                        kind=InferenceVariableKind.SAME_ENTITY,
                        states=(FALSE_STATE, TRUE_STATE),
                    )
                )
                factors.append(
                    InferenceFactor(
                        id=InferenceFactorId(
                            f"factor:entity-resolution:{enriched.left_entity_id}:{enriched.right_entity_id}"
                        ),
                        kind=InferenceFactorKind.EVIDENCE_PRIOR,
                        variable_ids=(variable_id,),
                        potentials=(1.0 - score, score),
                        evidence_ids=enriched.evidence_ids,
                        signals=tuple(
                            dict.fromkeys([*enriched.retrieval_signals, *enriched.context_signals])
                        ),
                    )
                )
                semantic_factor = self._semantic_same_entity_factor(
                    document=document,
                    variable_id=variable_id,
                    left_entity_id=enriched.left_entity_id,
                    right_entity_id=enriched.right_entity_id,
                )
                if semantic_factor is not None:
                    factors.append(semantic_factor)
                entity_proposal_by_variable_id[variable_id] = enriched
                same_entity_variable_id_by_pair[
                    self._entity_pair(enriched.left_entity_id, enriched.right_entity_id)
                ] = variable_id

    def _add_same_entity_role_factors(
        self,
        *,
        document: ArticleDocument,
        fact_graph: BuiltFactInferenceGraph,
        factors: list[InferenceFactor],
        same_entity_variable_id_by_pair: dict[
            tuple[EntityCandidateId, EntityCandidateId], InferenceVariableId
        ],
    ) -> None:
        for (
            left_entity_id,
            right_entity_id,
        ), same_entity_variable_id in same_entity_variable_id_by_pair.items():
            preferred_pair = self._descriptor_named_pair(
                document=document,
                left_entity_id=left_entity_id,
                right_entity_id=right_entity_id,
            )
            if preferred_pair is None:
                continue
            descriptor_entity_id, named_entity_id = preferred_pair
            for (
                role_variable_id,
                role_states,
            ) in fact_graph.index.filler_states_by_variable_id.items():
                entity_ids = {
                    entity_id
                    for state in role_states
                    for entity_id in [self._entity_id_from_state(state)]
                    if entity_id is not None
                }
                if descriptor_entity_id not in entity_ids or named_entity_id not in entity_ids:
                    continue
                factors.append(
                    self._same_entity_role_factor(
                        same_entity_variable_id=same_entity_variable_id,
                        role_variable_id=role_variable_id,
                        role_states=role_states,
                        descriptor_entity_id=descriptor_entity_id,
                        named_entity_id=named_entity_id,
                    )
                )

    def _same_entity_role_factor(
        self,
        *,
        same_entity_variable_id: InferenceVariableId,
        role_variable_id: InferenceVariableId,
        role_states: tuple[RoleFillerState, ...],
        descriptor_entity_id: EntityCandidateId,
        named_entity_id: EntityCandidateId,
    ) -> InferenceFactor:
        values: list[float] = []
        for same_entity_state in (FALSE_STATE, TRUE_STATE):
            for role_state in role_states:
                if same_entity_state.id == FALSE_STATE.id:
                    values.append(1.0)
                    continue
                role_entity_id = self._entity_id_from_state(role_state)
                if role_entity_id == descriptor_entity_id:
                    values.append(0.35)
                elif role_entity_id == named_entity_id:
                    values.append(1.2)
                else:
                    values.append(1.0)
        return InferenceFactor(
            id=InferenceFactorId(
                "factor:same-entity-role:"
                f"{descriptor_entity_id}:{named_entity_id}:{role_variable_id}"
            ),
            kind=InferenceFactorKind.CONSTRAINT,
            variable_ids=(same_entity_variable_id, role_variable_id),
            potentials=tuple(values),
        )

    def _add_reference_resolution_variables(
        self,
        *,
        document: ArticleDocument,
        variables: list[InferenceVariable],
        factors: list[InferenceFactor],
        reference_state_proposals_by_variable_id: dict[
            InferenceVariableId, dict[InferenceStateId, ReferenceResolutionProposal]
        ],
        reference_variable_id_by_reference_id: dict[MentionId, InferenceVariableId],
    ) -> None:
        signal_producer = EvidenceSignalProducer()
        scorer = ReferenceResolutionScorer(document.store)
        grouped: dict[MentionId, dict[EntityCandidateId, ReferenceResolutionProposal]] = {}
        for proposal in document.reference_resolution_proposals:
            enriched = signal_producer.enrich_reference_resolution_proposal(
                document.store,
                proposal,
            )
            grouped.setdefault(enriched.reference_id, {})[enriched.candidate_entity_id] = enriched
        for reference_key, proposal_map in grouped.items():
            ordered = [
                proposal_map[entity_id]
                for entity_id in sorted(proposal_map.keys(), key=lambda item: str(item))
            ]
            if not ordered:
                continue
            variable_id = InferenceVariableId(f"reference-target:{reference_key}")
            states = [UNKNOWN_STATE]
            weights = [
                self._unknown_weight(tuple(scorer.score(proposal).score for proposal in ordered))
            ]
            state_map: dict[InferenceStateId, ReferenceResolutionProposal] = {}
            evidence_ids: list = []
            signals: list[Signal] = []
            semantic_potentials: list[float] = [1.0]
            semantic_evidence_ids: list[EvidenceId] = []
            semantic_signals: list[Signal] = []
            for proposal in ordered:
                state_id = self._reference_state_id_for_entity(proposal.candidate_entity_id)
                states.append(InferenceState(state_id, str(proposal.candidate_entity_id)))
                weights.append(scorer.score(proposal).score)
                state_map[state_id] = proposal
                evidence_ids.extend(proposal.evidence_ids)
                signals.extend(proposal.retrieval_signals)
                signals.extend(proposal.context_signals)
                semantic_match = self._semantic_reference_similarity(
                    document=document,
                    reference_id=proposal.reference_id,
                    candidate_entity_id=proposal.candidate_entity_id,
                )
                if semantic_match is None:
                    semantic_potentials.append(1.0)
                    continue
                semantic_evidence_pair, semantic_score = semantic_match
                semantic_potentials.append(1.25)
                semantic_evidence_ids.extend(semantic_evidence_pair)
                semantic_signals.append(SemanticEvidenceSimilaritySignal(score=semantic_score))
            variables.append(
                InferenceVariable(
                    id=variable_id,
                    kind=InferenceVariableKind.REFERENCE_TARGET,
                    states=tuple(states),
                )
            )
            factors.append(
                InferenceFactor(
                    id=InferenceFactorId(f"factor:reference-target:{reference_key}"),
                    kind=InferenceFactorKind.EVIDENCE_PRIOR,
                    variable_ids=(variable_id,),
                    potentials=self._normalize(tuple(weights)),
                    evidence_ids=tuple(dict.fromkeys(evidence_ids)),
                    signals=tuple(dict.fromkeys(signals)),
                )
            )
            if semantic_signals:
                factors.append(
                    InferenceFactor(
                        id=InferenceFactorId(f"factor:semantic-reference-target:{reference_key}"),
                        kind=InferenceFactorKind.EVIDENCE_PRIOR,
                        variable_ids=(variable_id,),
                        potentials=tuple(semantic_potentials),
                        evidence_ids=tuple(dict.fromkeys(semantic_evidence_ids)),
                        signals=tuple(dict.fromkeys(semantic_signals)),
                    )
                )
            reference_state_proposals_by_variable_id[variable_id] = state_map
            reference_variable_id_by_reference_id[ordered[0].reference_id] = variable_id

    def _add_self_tie_entity_factors(
        self,
        *,
        document: ArticleDocument,
        fact_graph: BuiltFactInferenceGraph,
        factors: list[InferenceFactor],
        same_entity_variable_id_by_pair: dict[
            tuple[EntityCandidateId, EntityCandidateId], InferenceVariableId
        ],
    ) -> None:
        for event in document.store.event_candidates.values():
            if event.kind is not FactKind.PERSONAL_OR_POLITICAL_TIE:
                continue
            subject_var_id = fact_graph.index.role_variable_id_by_event_role.get(
                (event.id, EventRole.SUBJECT)
            )
            object_var_id = fact_graph.index.role_variable_id_by_event_role.get(
                (event.id, EventRole.OBJECT)
            )
            if subject_var_id is None or object_var_id is None:
                continue
            subject_states = fact_graph.index.filler_states_by_variable_id.get(subject_var_id, ())
            object_states = fact_graph.index.filler_states_by_variable_id.get(object_var_id, ())
            seen_pairs: set[tuple[EntityCandidateId, EntityCandidateId]] = set()
            for s_state in subject_states:
                for o_state in object_states:
                    s_eid = None
                    o_eid = None
                    match s_state.filler:
                        case EntityFiller(entity_id=eid):
                            s_eid = eid
                    match o_state.filler:
                        case EntityFiller(entity_id=eid):
                            o_eid = eid
                    if s_eid is None or o_eid is None or s_eid == o_eid:
                        continue
                    pair = self._entity_pair(s_eid, o_eid)
                    same_entity_var_id = same_entity_variable_id_by_pair.get(pair)
                    if same_entity_var_id is None or pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    factors.append(
                        self._self_tie_entity_factor(
                            same_entity_variable_id=same_entity_var_id,
                            subject_variable_id=subject_var_id,
                            object_variable_id=object_var_id,
                            subject_states=subject_states,
                            object_states=object_states,
                            left_entity_id=pair[0],
                            right_entity_id=pair[1],
                            event_id=event.id,
                        )
                    )

    def _self_tie_entity_factor(
        self,
        *,
        same_entity_variable_id: InferenceVariableId,
        subject_variable_id: InferenceVariableId,
        object_variable_id: InferenceVariableId,
        subject_states: tuple[RoleFillerState, ...],
        object_states: tuple[RoleFillerState, ...],
        left_entity_id: EntityCandidateId,
        right_entity_id: EntityCandidateId,
        event_id: EventCandidateId,
    ) -> InferenceFactor:
        values: list[float] = []
        for same_entity_state in (FALSE_STATE, TRUE_STATE):
            for s_state in subject_states:
                for o_state in object_states:
                    if same_entity_state.id == FALSE_STATE.id:
                        values.append(1.0)
                        continue
                    s_eid = None
                    o_eid = None
                    match s_state.filler:
                        case EntityFiller(entity_id=eid):
                            s_eid = eid
                    match o_state.filler:
                        case EntityFiller(entity_id=eid):
                            o_eid = eid
                    if (s_eid, o_eid) in (
                        (left_entity_id, right_entity_id),
                        (right_entity_id, left_entity_id),
                    ):
                        values.append(0.000001)
                    else:
                        values.append(1.0)
        return InferenceFactor(
            id=InferenceFactorId(
                f"factor:self-tie-entity:{event_id}:{left_entity_id}:{right_entity_id}"
            ),
            kind=InferenceFactorKind.CONSTRAINT,
            variable_ids=(same_entity_variable_id, subject_variable_id, object_variable_id),
            potentials=tuple(values),
        )

    def _add_entity_context_variables(
        self,
        *,
        document: ArticleDocument,
        variables: list[InferenceVariable],
        factors: list[InferenceFactor],
        entity_context_proposal_by_variable_id: dict[InferenceVariableId, EntityContextProposal],
        entity_context_variable_id_by_pair: dict[
            tuple[EntityCandidateId, EntityTag], InferenceVariableId
        ],
    ) -> None:
        for proposal in self._merged_entity_context_proposals(document):
            pair_key = (proposal.entity_id, proposal.context_kind)
            variable_id = InferenceVariableId(
                f"entity-context:{proposal.entity_id}:{proposal.context_kind.value}"
            )
            variables.append(
                InferenceVariable(
                    id=variable_id,
                    kind=InferenceVariableKind.ENTITY_ATTRIBUTE,
                    states=(FALSE_STATE, TRUE_STATE),
                )
            )
            prior = self.entity_context_scorer.score(proposal).score
            factors.append(
                InferenceFactor(
                    id=InferenceFactorId(
                        f"factor:entity-context-prior:{proposal.entity_id}:"
                        f"{proposal.context_kind.value}"
                    ),
                    kind=InferenceFactorKind.EVIDENCE_PRIOR,
                    variable_ids=(variable_id,),
                    potentials=(1.0 - prior, prior),
                    evidence_ids=proposal.evidence_ids,
                    signals=proposal.retrieval_signals,
                )
            )
            entity_context_proposal_by_variable_id[variable_id] = proposal
            entity_context_variable_id_by_pair[pair_key] = variable_id

    def _merged_entity_context_proposals(
        self,
        document: ArticleDocument,
    ) -> tuple[EntityContextProposal, ...]:
        merged: dict[tuple[EntityCandidateId, EntityTag], EntityContextProposal] = {}
        for proposal in document.entity_context_proposals:
            pair_key = (proposal.entity_id, proposal.context_kind)
            current = merged.get(pair_key)
            if current is None:
                merged[pair_key] = proposal
                continue
            merged[pair_key] = EntityContextProposal(
                entity_id=proposal.entity_id,
                context_kind=proposal.context_kind,
                evidence_ids=tuple(dict.fromkeys([*current.evidence_ids, *proposal.evidence_ids])),
                retrieval_signals=tuple(
                    dict.fromkeys([*current.retrieval_signals, *proposal.retrieval_signals])
                ),
            )
        return tuple(
            merged[key] for key in sorted(merged, key=lambda item: (str(item[0]), item[1].value))
        )

    def _add_entity_context_role_factors(
        self,
        *,
        fact_graph: BuiltFactInferenceGraph,
        factors: list[InferenceFactor],
        entity_context_variable_id_by_pair: dict[
            tuple[EntityCandidateId, EntityTag], InferenceVariableId
        ],
    ) -> None:
        if not entity_context_variable_id_by_pair:
            return
        role_variables = {
            variable.id: variable
            for variable in fact_graph.spec.variables
            if variable.kind is InferenceVariableKind.ROLE_FILLER
        }
        for role_variable_id, role_states in fact_graph.index.filler_states_by_variable_id.items():
            role_variable = role_variables.get(role_variable_id)
            if role_variable is None:
                continue
            fact_kind = role_variable.fact_kind
            role = role_variable.role
            if fact_kind is None or role is None:
                continue
            for tag in EntityTag:
                potential = self.entity_context_role_policy.potential(
                    tag=tag, fact_kind=fact_kind, role=role
                )
                if potential == 1.0:
                    continue
                for state in role_states:
                    entity_id = self._entity_id_from_state(state)
                    if entity_id is None:
                        continue
                    context_variable_id = entity_context_variable_id_by_pair.get((entity_id, tag))
                    if context_variable_id is None:
                        continue
                    factors.append(
                        self._entity_context_role_factor(
                            context_variable_id=context_variable_id,
                            role_variable_id=role_variable_id,
                            role_states=role_states,
                            target_entity_id=entity_id,
                            potential=potential,
                            tag=tag,
                        )
                    )

    def _entity_context_role_factor(
        self,
        *,
        context_variable_id: InferenceVariableId,
        role_variable_id: InferenceVariableId,
        role_states: tuple[RoleFillerState, ...],
        target_entity_id: EntityCandidateId,
        potential: float,
        tag: EntityTag,
    ) -> InferenceFactor:
        values: list[float] = []
        for context_state in (FALSE_STATE, TRUE_STATE):
            for role_state in role_states:
                if context_state.id == FALSE_STATE.id:
                    values.append(1.0)
                    continue
                role_entity_id = self._entity_id_from_state(role_state)
                if role_entity_id == target_entity_id:
                    values.append(potential)
                else:
                    values.append(1.0)
        return InferenceFactor(
            id=InferenceFactorId(
                f"factor:entity-context-role:{target_entity_id}:{tag.value}:{role_variable_id}"
            ),
            kind=InferenceFactorKind.CONSTRAINT,
            variable_ids=(context_variable_id, role_variable_id),
            potentials=tuple(values),
        )

    def _add_reference_role_factors(
        self,
        *,
        document: ArticleDocument,
        fact_graph: BuiltFactInferenceGraph,
        factors: list[InferenceFactor],
        reference_variable_id_by_reference_id: dict[MentionId, InferenceVariableId],
        reference_state_proposals_by_variable_id: dict[
            InferenceVariableId, dict[InferenceStateId, ReferenceResolutionProposal]
        ],
    ) -> None:
        role_variables = {
            variable.id: variable
            for variable in fact_graph.spec.variables
            if variable.kind is InferenceVariableKind.ROLE_FILLER
        }
        for role_variable_id, role_states in fact_graph.index.filler_states_by_variable_id.items():
            role_variable = role_variables.get(role_variable_id)
            if role_variable is None:
                continue
            allowed_entity_kinds: frozenset[EntityKind] = frozenset(EntityKind)
            if role_variable.fact_kind is not None and role_variable.role is not None:
                role_spec = schema_for(role_variable.fact_kind).role_spec_for(role_variable.role)
                if role_spec is not None:
                    allowed_entity_kinds = role_spec.allowed_entity_kinds
            for (
                reference_id,
                reference_variable_id,
            ) in reference_variable_id_by_reference_id.items():
                if not any(
                    self._state_depends_on_reference(document, state, reference_id)
                    for state in role_states
                ):
                    continue
                state_proposals = reference_state_proposals_by_variable_id.get(
                    reference_variable_id, {}
                )
                reference_state_ids = (UNKNOWN_STATE.id, *tuple(state_proposals.keys()))
                state_entity_by_state_id: dict[InferenceStateId, EntityCandidateId] = {
                    state_id: proposal.candidate_entity_id
                    for state_id, proposal in state_proposals.items()
                }
                factors.append(
                    self._reference_role_factor(
                        role_variable_id=role_variable_id,
                        role_states=role_states,
                        reference_id=reference_id,
                        reference_variable_id=reference_variable_id,
                        reference_state_ids=reference_state_ids,
                        state_entity_by_state_id=state_entity_by_state_id,
                        allowed_entity_kinds=allowed_entity_kinds,
                        document=document,
                    )
                )

    def _add_same_event_variables(
        self,
        *,
        document: ArticleDocument,
        fact_graph: BuiltFactInferenceGraph,
        variables: list[InferenceVariable],
        factors: list[InferenceFactor],
        same_entity_variable_id_by_pair: dict[
            tuple[EntityCandidateId, EntityCandidateId], InferenceVariableId
        ],
        same_event_proposal_by_variable_id: dict[InferenceVariableId, SameEventProposal],
    ) -> None:
        event_views = self._event_views(document)
        event_variable_id_by_event_id = {
            event_id: variable_id
            for variable_id, event_id in fact_graph.index.event_id_by_event_variable_id.items()
        }
        fact_id_by_event_id = {
            event_id: fact_graph.index.fact_id_by_event_variable_id[variable_id]
            for variable_id, event_id in fact_graph.index.event_id_by_event_variable_id.items()
        }
        proposals = self._same_event_proposals(
            document=document,
            event_views=event_views,
            fact_id_by_event_id=fact_id_by_event_id,
            same_entity_variable_id_by_pair=same_entity_variable_id_by_pair,
        )
        for proposal in proposals:
            variable_id = InferenceVariableId(
                f"same-event:{proposal.fact_proposal.left_fact_id}:{proposal.fact_proposal.right_fact_id}"
            )
            variables.append(
                InferenceVariable(
                    id=variable_id,
                    kind=InferenceVariableKind.SAME_EVENT,
                    states=(FALSE_STATE, TRUE_STATE),
                    fact_kind=document.store.event_candidates[proposal.left_event_id].kind,
                )
            )
            factors.append(
                InferenceFactor(
                    id=InferenceFactorId(
                        f"factor:same-event-prior:{proposal.fact_proposal.left_fact_id}:{proposal.fact_proposal.right_fact_id}"
                    ),
                    kind=InferenceFactorKind.EVIDENCE_PRIOR,
                    variable_ids=(variable_id,),
                    potentials=self._same_event_prior(proposal.strategy),
                    evidence_ids=proposal.fact_proposal.evidence_ids,
                    signals=proposal.fact_proposal.retrieval_signals,
                )
            )
            left_event_variable_id = event_variable_id_by_event_id[proposal.left_event_id]
            right_event_variable_id = event_variable_id_by_event_id[proposal.right_event_id]
            factors.append(
                self._same_event_activity_factor(
                    same_event_variable_id=variable_id,
                    left_event_variable_id=left_event_variable_id,
                    right_event_variable_id=right_event_variable_id,
                    left_fact_id=proposal.fact_proposal.left_fact_id,
                    right_fact_id=proposal.fact_proposal.right_fact_id,
                )
            )
            for left_entity_id, right_entity_id in proposal.linked_entity_pairs:
                same_entity_variable_id = same_entity_variable_id_by_pair.get(
                    self._entity_pair(left_entity_id, right_entity_id)
                )
                if same_entity_variable_id is None:
                    continue
                factors.append(
                    self._same_event_entity_factor(
                        same_event_variable_id=variable_id,
                        same_entity_variable_id=same_entity_variable_id,
                        left_fact_id=proposal.fact_proposal.left_fact_id,
                        right_fact_id=proposal.fact_proposal.right_fact_id,
                        left_entity_id=left_entity_id,
                        right_entity_id=right_entity_id,
                    )
                )
            same_event_proposal_by_variable_id[variable_id] = proposal

    def _event_views(self, document: ArticleDocument) -> dict[EventCandidateId, _EventBindingView]:
        views: dict[EventCandidateId, _EventBindingView] = {}
        for event in document.store.event_candidates.values():
            schema = schema_for(event.kind)
            entity_fillers: dict[FactArgumentRole, set[EntityCandidateId]] = {}
            text_fillers: dict[FactArgumentRole, set[str]] = {}
            entity_groundings: dict[FactArgumentRole, list[GroundingKind]] = {}
            for binding in document.store.argument_bindings_for_event(event.id):
                output_role = schema.output_role_for_event_role(binding.role)
                if output_role is FactArgumentRole.ACTOR:
                    continue
                match binding.filler:
                    case EntityFiller(entity_id=entity_id):
                        entity_fillers.setdefault(output_role, set()).add(entity_id)
                        entity = document.store.entity_candidates.get(entity_id)
                        if entity is not None:
                            entity_groundings.setdefault(output_role, []).append(entity.grounding)
                    case TextFiller(value=value):
                        text_fillers.setdefault(output_role, set()).add(value.casefold())
            views[event.id] = _EventBindingView(
                kind=event.kind,
                entity_fillers={role: frozenset(values) for role, values in entity_fillers.items()},
                text_fillers={role: frozenset(values) for role, values in text_fillers.items()},
                entity_groundings={
                    role: tuple(values) for role, values in entity_groundings.items()
                },
            )
        return views

    def _same_event_proposals(
        self,
        *,
        document: ArticleDocument,
        event_views: dict[EventCandidateId, _EventBindingView],
        fact_id_by_event_id: dict[EventCandidateId, FactCandidateId],
        same_entity_variable_id_by_pair: dict[
            tuple[EntityCandidateId, EntityCandidateId], InferenceVariableId
        ],
    ) -> tuple[SameEventProposal, ...]:
        event_ids: list[EventCandidateId] = list(event_views.keys())
        event_ids.sort(key=lambda item: str(item))
        proposals: list[SameEventProposal] = []
        for index, left_event_id in enumerate(event_ids):
            left = event_views[left_event_id]
            for right_event_id in event_ids[index + 1 :]:
                right = event_views[right_event_id]
                if left.kind is not right.kind:
                    continue
                strategy = self._same_event_strategy(left, right, same_entity_variable_id_by_pair)
                semantic_match = self._semantic_event_similarity(
                    document=document,
                    left_event_id=left_event_id,
                    right_event_id=right_event_id,
                )
                if strategy is None:
                    if semantic_match is None:
                        continue
                    strategy = FactResolutionStrategy.SEMANTIC_EVIDENCE
                linked_entity_pairs = self._linked_entity_pairs(
                    left, right, strategy, same_entity_variable_id_by_pair
                )
                evidence_ids = semantic_match[0] if semantic_match is not None else ()
                signals: tuple[Signal, ...] = (
                    DuplicateFactSignal(strategy=strategy, fact_kind=left.kind),
                )
                if semantic_match is not None:
                    signals = (
                        *signals,
                        SemanticEvidenceSimilaritySignal(score=semantic_match[1]),
                    )
                proposals.append(
                    SameEventProposal(
                        left_event_id=left_event_id,
                        right_event_id=right_event_id,
                        strategy=strategy,
                        fact_proposal=FactResolutionProposal(
                            left_fact_id=fact_id_by_event_id[left_event_id],
                            right_fact_id=fact_id_by_event_id[right_event_id],
                            relation=ResolutionRelation.SAME_FACT,
                            evidence_ids=evidence_ids,
                            retrieval_signals=signals,
                        ),
                        linked_entity_pairs=linked_entity_pairs,
                    )
                )
        return tuple(proposals)

    def _semantic_event_similarity(
        self,
        *,
        document: ArticleDocument,
        left_event_id: EventCandidateId,
        right_event_id: EventCandidateId,
    ) -> tuple[tuple[EvidenceId, EvidenceId], float] | None:
        return self._semantic_evidence_similarity(
            document=document,
            left_evidence_ids=self._event_evidence_ids(document, left_event_id),
            right_evidence_ids=self._event_evidence_ids(document, right_event_id),
            threshold=self.semantic_same_event_threshold,
        )

    def _semantic_same_entity_factor(
        self,
        *,
        document: ArticleDocument,
        variable_id: InferenceVariableId,
        left_entity_id: EntityCandidateId,
        right_entity_id: EntityCandidateId,
    ) -> InferenceFactor | None:
        semantic_match = self._semantic_entity_similarity(
            document=document,
            left_entity_id=left_entity_id,
            right_entity_id=right_entity_id,
        )
        if semantic_match is None:
            return None
        evidence_pair, score = semantic_match
        return InferenceFactor(
            id=InferenceFactorId(f"factor:semantic-same-entity:{left_entity_id}:{right_entity_id}"),
            kind=InferenceFactorKind.EVIDENCE_PRIOR,
            variable_ids=(variable_id,),
            potentials=(1.0, 1.15),
            evidence_ids=evidence_pair,
            signals=(SemanticEvidenceSimilaritySignal(score=score),),
        )

    def _semantic_reference_similarity(
        self,
        *,
        document: ArticleDocument,
        reference_id: MentionId,
        candidate_entity_id: EntityCandidateId,
    ) -> tuple[tuple[EvidenceId, EvidenceId], float] | None:
        reference = document.store.references.get(reference_id)
        if reference is None:
            return None
        return self._semantic_evidence_similarity(
            document=document,
            left_evidence_ids=(reference.evidence_id,),
            right_evidence_ids=self._entity_evidence_ids(document, candidate_entity_id),
            threshold=self.semantic_reference_threshold,
        )

    def _semantic_entity_similarity(
        self,
        *,
        document: ArticleDocument,
        left_entity_id: EntityCandidateId,
        right_entity_id: EntityCandidateId,
    ) -> tuple[tuple[EvidenceId, EvidenceId], float] | None:
        return self._semantic_evidence_similarity(
            document=document,
            left_evidence_ids=self._entity_evidence_ids(document, left_entity_id),
            right_evidence_ids=self._entity_evidence_ids(document, right_entity_id),
            threshold=self.semantic_same_entity_threshold,
        )

    def _semantic_entity_proposals(
        self,
        *,
        document: ArticleDocument,
        entity: EntityCandidate,
        entity_ids_by_evidence_id: dict[EvidenceId, tuple[EntityCandidateId, ...]],
    ) -> tuple[EntityResolutionProposal, ...]:
        if not entity.mention_ids and not entity.reference_ids:
            return ()
        proposals: list[EntityResolutionProposal] = []
        seen: set[EntityCandidateId] = set()
        for evidence_id in self._entity_evidence_ids(document, entity.id):
            vector = document.evidence_index.vector_for(evidence_id)
            if vector is None:
                continue
            for match in document.evidence_index.search(
                vector,
                limit=8,
                min_score=self.semantic_same_entity_threshold,
            ):
                for other_id in entity_ids_by_evidence_id.get(match.evidence_id, ()):
                    if other_id == entity.id or other_id in seen:
                        continue
                    other = document.store.entity_candidates.get(other_id)
                    if other is None or other.kind is not entity.kind:
                        continue
                    seen.add(other_id)
                    proposals.append(
                        EntityResolutionProposal(
                            left_entity_id=entity.id,
                            right_entity_id=other_id,
                            evidence_ids=(evidence_id, match.evidence_id),
                            retrieval_signals=(
                                SemanticEvidenceSimilaritySignal(score=match.score),
                            ),
                        )
                    )
        return tuple(proposals)

    def _semantic_evidence_similarity(
        self,
        *,
        document: ArticleDocument,
        left_evidence_ids: tuple[EvidenceId, ...],
        right_evidence_ids: tuple[EvidenceId, ...],
        threshold: float,
    ) -> tuple[tuple[EvidenceId, EvidenceId], float] | None:
        best: tuple[tuple[EvidenceId, EvidenceId], float] | None = None
        right_evidence_set = frozenset(right_evidence_ids)
        for left_evidence_id in left_evidence_ids:
            left_vector = document.evidence_index.vector_for(left_evidence_id)
            if left_vector is None:
                continue
            for match in document.evidence_index.search(
                left_vector,
                limit=8,
                min_score=threshold,
            ):
                if match.evidence_id not in right_evidence_set:
                    continue
                evidence_pair = (left_evidence_id, match.evidence_id)
                if best is None or match.score > best[1]:
                    best = (evidence_pair, match.score)
        return best

    def _entity_ids_by_evidence_id(
        self,
        document: ArticleDocument,
    ) -> dict[EvidenceId, tuple[EntityCandidateId, ...]]:
        entity_ids_by_evidence_id: dict[EvidenceId, list[EntityCandidateId]] = {}
        for entity_id in document.store.entity_candidates:
            for evidence_id in self._entity_evidence_ids(document, entity_id):
                entity_ids_by_evidence_id.setdefault(evidence_id, []).append(entity_id)
        return {
            evidence_id: tuple(entity_ids)
            for evidence_id, entity_ids in entity_ids_by_evidence_id.items()
        }

    def _entity_evidence_ids(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
    ) -> tuple[EvidenceId, ...]:
        entity = document.store.entity_candidates.get(entity_id)
        if entity is None:
            return ()
        evidence_ids: list[EvidenceId] = []
        for mention_id in entity.mention_ids:
            mention = document.store.mentions.get(mention_id)
            if mention is not None:
                evidence_ids.append(mention.evidence_id)
        for reference_id in entity.reference_ids:
            reference = document.store.references.get(reference_id)
            if reference is not None:
                evidence_ids.append(reference.evidence_id)
        return tuple(dict.fromkeys(evidence_ids))

    def _descriptor_named_pair(
        self,
        *,
        document: ArticleDocument,
        left_entity_id: EntityCandidateId,
        right_entity_id: EntityCandidateId,
    ) -> tuple[EntityCandidateId, EntityCandidateId] | None:
        left = document.store.entity_candidates.get(left_entity_id)
        right = document.store.entity_candidates.get(right_entity_id)
        if left is None or right is None:
            return None
        if left.kind is not EntityKind.PERSON or right.kind is not EntityKind.PERSON:
            return None
        if (
            self._is_descriptor_person(document, left_entity_id)
            and right.grounding is GroundingKind.OBSERVED
        ):
            return (left_entity_id, right_entity_id)
        if (
            self._is_descriptor_person(document, right_entity_id)
            and left.grounding is GroundingKind.OBSERVED
        ):
            return (right_entity_id, left_entity_id)
        return None

    def _is_descriptor_person(
        self,
        document: ArticleDocument,
        entity_id: EntityCandidateId,
    ) -> bool:
        entity = document.store.entity_candidates.get(entity_id)
        if entity is None or entity.kind is not EntityKind.PERSON:
            return False
        if entity.grounding is GroundingKind.INFERRED:
            return True
        return any(
            mention.kind is MentionKind.DESCRIPTOR_NOUN_PHRASE
            for mention in document.store.candidate_mentions(entity_id)
        )

    def _event_evidence_ids(
        self,
        document: ArticleDocument,
        event_id: EventCandidateId,
    ) -> tuple[EvidenceId, ...]:
        event = document.store.event_candidates[event_id]
        evidence_ids = list(event.evidence_ids)
        if event.trigger_evidence_id is not None:
            evidence_ids.append(event.trigger_evidence_id)
        for binding in document.store.argument_bindings_for_event(event_id):
            evidence_ids.extend(binding.evidence_ids)
        return tuple(dict.fromkeys(evidence_ids))

    def _same_event_strategy(
        self,
        left: _EventBindingView,
        right: _EventBindingView,
        same_entity_variable_id_by_pair: dict[
            tuple[EntityCandidateId, EntityCandidateId], InferenceVariableId
        ],
    ) -> FactResolutionStrategy | None:
        if left.entity_fillers == right.entity_fillers and left.text_fillers == right.text_fillers:
            return FactResolutionStrategy.EXACT_ARGUMENTS
        if left.kind in {
            FactKind.GOVERNANCE_APPOINTMENT,
            FactKind.GOVERNANCE_DISMISSAL,
        } and self._without_roles(left) == self._without_roles(right):
            return FactResolutionStrategy.GOVERNANCE_ROLE_RELAXED
        if left.kind is FactKind.PERSONAL_OR_POLITICAL_TIE:
            left_object = left.entity_fillers.get(FactArgumentRole.OBJECT, frozenset())
            right_object = right.entity_fillers.get(FactArgumentRole.OBJECT, frozenset())
            left_detail = left.text_fillers.get(FactArgumentRole.RELATIONSHIP_DETAIL, frozenset())
            right_detail = right.text_fillers.get(FactArgumentRole.RELATIONSHIP_DETAIL, frozenset())
            object_pair = self._aligned_single_filler_pair_with_resolution(
                left_fillers=left_object,
                right_fillers=right_object,
                same_entity_variable_id_by_pair=same_entity_variable_id_by_pair,
            )
            if (
                (left_object != right_object and object_pair is None)
                or left_detail != right_detail
                or not left_detail
            ):
                return None
            left_subject = left.entity_fillers.get(FactArgumentRole.SUBJECT, frozenset())
            right_subject = right.entity_fillers.get(FactArgumentRole.SUBJECT, frozenset())
            left_proxy = GroundingKind.PROXY in left.entity_groundings.get(
                FactArgumentRole.SUBJECT,
                (),
            )
            right_proxy = GroundingKind.PROXY in right.entity_groundings.get(
                FactArgumentRole.SUBJECT,
                (),
            )
            if left_subject == right_subject:
                return FactResolutionStrategy.TIE_CONTEXT_RELAXED
            if left_subject != right_subject and (left_proxy or right_proxy):
                return FactResolutionStrategy.PROXY_NAMED_TIE
            return None
        if left.text_fillers == right.text_fillers:
            if same_entity_variable_id_by_pair:
                aligned = self._aligned_entity_pairs_with_resolution(
                    left, right, same_entity_variable_id_by_pair
                )
            else:
                aligned = self._aligned_entity_pairs(left, right)
            if aligned:
                return FactResolutionStrategy.ENTITY_ALIGNMENT_RELAXED
        return None

    def _linked_entity_pairs(
        self,
        left: _EventBindingView,
        right: _EventBindingView,
        strategy: FactResolutionStrategy,
        same_entity_variable_id_by_pair: dict[
            tuple[EntityCandidateId, EntityCandidateId], InferenceVariableId
        ],
    ) -> tuple[tuple[EntityCandidateId, EntityCandidateId], ...]:
        if strategy is FactResolutionStrategy.PROXY_NAMED_TIE:
            linked_pairs: list[tuple[EntityCandidateId, EntityCandidateId]] = []
            subject_pair = self._aligned_single_filler_pair_with_resolution(
                left_fillers=left.entity_fillers.get(FactArgumentRole.SUBJECT, frozenset()),
                right_fillers=right.entity_fillers.get(FactArgumentRole.SUBJECT, frozenset()),
                same_entity_variable_id_by_pair=same_entity_variable_id_by_pair,
            )
            if subject_pair is not None:
                linked_pairs.append(subject_pair)
            object_pair = self._aligned_single_filler_pair_with_resolution(
                left_fillers=left.entity_fillers.get(FactArgumentRole.OBJECT, frozenset()),
                right_fillers=right.entity_fillers.get(FactArgumentRole.OBJECT, frozenset()),
                same_entity_variable_id_by_pair=same_entity_variable_id_by_pair,
            )
            if object_pair is not None:
                linked_pairs.append(object_pair)
            return tuple(linked_pairs)
        if strategy is FactResolutionStrategy.TIE_CONTEXT_RELAXED:
            object_pair = self._aligned_single_filler_pair_with_resolution(
                left_fillers=left.entity_fillers.get(FactArgumentRole.OBJECT, frozenset()),
                right_fillers=right.entity_fillers.get(FactArgumentRole.OBJECT, frozenset()),
                same_entity_variable_id_by_pair=same_entity_variable_id_by_pair,
            )
            return (object_pair,) if object_pair is not None else ()
        if strategy is FactResolutionStrategy.ENTITY_ALIGNMENT_RELAXED:
            if same_entity_variable_id_by_pair:
                return self._aligned_entity_pairs_with_resolution(
                    left, right, same_entity_variable_id_by_pair
                )
            else:
                return self._aligned_entity_pairs(left, right)
        return ()

    def _aligned_entity_pairs(
        self,
        left: _EventBindingView,
        right: _EventBindingView,
    ) -> tuple[tuple[EntityCandidateId, EntityCandidateId], ...]:
        linked_pairs: list[tuple[EntityCandidateId, EntityCandidateId]] = []
        for role in sorted(
            set(left.entity_fillers) | set(right.entity_fillers),
            key=lambda item: item.value,
        ):
            left_fillers = left.entity_fillers.get(role, frozenset())
            right_fillers = right.entity_fillers.get(role, frozenset())
            if left_fillers == right_fillers:
                continue
            if len(left_fillers) != 1 or len(right_fillers) != 1:
                return ()
            left_entity_id = next(iter(left_fillers))
            right_entity_id = next(iter(right_fillers))
            if left_entity_id == right_entity_id:
                continue
            linked_pairs.append(self._entity_pair(left_entity_id, right_entity_id))
        return tuple(linked_pairs)

    def _aligned_entity_pairs_with_resolution(
        self,
        left: _EventBindingView,
        right: _EventBindingView,
        same_entity_variable_id_by_pair: dict[
            tuple[EntityCandidateId, EntityCandidateId], InferenceVariableId
        ],
    ) -> tuple[tuple[EntityCandidateId, EntityCandidateId], ...]:
        linked_pairs: list[tuple[EntityCandidateId, EntityCandidateId]] = []
        for role in sorted(
            set(left.entity_fillers) | set(right.entity_fillers),
            key=lambda item: item.value,
        ):
            left_fillers = left.entity_fillers.get(role, frozenset())
            right_fillers = right.entity_fillers.get(role, frozenset())
            if left_fillers == right_fillers:
                continue
            if len(left_fillers) != 1 or len(right_fillers) != 1:
                return ()
            left_entity_id = next(iter(left_fillers))
            right_entity_id = next(iter(right_fillers))
            if left_entity_id == right_entity_id:
                continue
            pair = self._entity_pair(left_entity_id, right_entity_id)
            if pair not in same_entity_variable_id_by_pair:
                return ()
            linked_pairs.append(pair)
        return tuple(linked_pairs)

    def _aligned_single_filler_pair_with_resolution(
        self,
        *,
        left_fillers: frozenset[EntityCandidateId],
        right_fillers: frozenset[EntityCandidateId],
        same_entity_variable_id_by_pair: dict[
            tuple[EntityCandidateId, EntityCandidateId], InferenceVariableId
        ],
    ) -> tuple[EntityCandidateId, EntityCandidateId] | None:
        if left_fillers == right_fillers:
            return None
        if len(left_fillers) != 1 or len(right_fillers) != 1:
            return None
        left_entity_id = next(iter(left_fillers))
        right_entity_id = next(iter(right_fillers))
        if left_entity_id == right_entity_id:
            return None
        pair = self._entity_pair(left_entity_id, right_entity_id)
        if pair not in same_entity_variable_id_by_pair:
            return None
        return pair

    def _without_roles(
        self,
        view: _EventBindingView,
    ) -> tuple[
        tuple[tuple[FactArgumentRole, frozenset[EntityCandidateId]], ...],
        tuple[tuple[FactArgumentRole, frozenset[str]], ...],
    ]:
        return (
            tuple(
                sorted(
                    (
                        (role, fillers)
                        for role, fillers in view.entity_fillers.items()
                        if role is not FactArgumentRole.ROLE
                    ),
                    key=lambda item: item[0].value,
                )
            ),
            tuple(
                sorted(
                    (
                        (role, fillers)
                        for role, fillers in view.text_fillers.items()
                        if role is not FactArgumentRole.CONTEXT
                    ),
                    key=lambda item: item[0].value,
                )
            ),
        )

    def _same_event_activity_factor(
        self,
        *,
        same_event_variable_id: InferenceVariableId,
        left_event_variable_id: InferenceVariableId,
        right_event_variable_id: InferenceVariableId,
        left_fact_id: FactCandidateId,
        right_fact_id: FactCandidateId,
    ) -> InferenceFactor:
        values: list[float] = []
        for same_event_state in (FALSE_STATE, TRUE_STATE):
            for left_event_state in (FALSE_STATE, TRUE_STATE):
                for right_event_state in (FALSE_STATE, TRUE_STATE):
                    if same_event_state.id == FALSE_STATE.id:
                        values.append(1.0)
                        continue
                    if (
                        left_event_state.id == TRUE_STATE.id
                        and right_event_state.id == TRUE_STATE.id
                    ):
                        values.append(1.0)
                    elif (
                        left_event_state.id == TRUE_STATE.id
                        or right_event_state.id == TRUE_STATE.id
                    ):
                        values.append(0.2)
                    else:
                        values.append(0.05)
        return InferenceFactor(
            id=InferenceFactorId(f"factor:same-event-activity:{left_fact_id}:{right_fact_id}"),
            kind=InferenceFactorKind.CONSTRAINT,
            variable_ids=(same_event_variable_id, left_event_variable_id, right_event_variable_id),
            potentials=tuple(values),
        )

    def _same_event_entity_factor(
        self,
        *,
        same_event_variable_id: InferenceVariableId,
        same_entity_variable_id: InferenceVariableId,
        left_fact_id: FactCandidateId,
        right_fact_id: FactCandidateId,
        left_entity_id: EntityCandidateId,
        right_entity_id: EntityCandidateId,
    ) -> InferenceFactor:
        values: list[float] = []
        for same_event_state in (FALSE_STATE, TRUE_STATE):
            for same_entity_state in (FALSE_STATE, TRUE_STATE):
                if same_event_state.id == FALSE_STATE.id:
                    values.append(1.0)
                elif same_entity_state.id == TRUE_STATE.id:
                    values.append(1.0)
                else:
                    values.append(0.25)
        return InferenceFactor(
            id=InferenceFactorId(
                f"factor:same-event-entity:{left_fact_id}:{right_fact_id}:{left_entity_id}:{right_entity_id}"
            ),
            kind=InferenceFactorKind.CONSTRAINT,
            variable_ids=(same_event_variable_id, same_entity_variable_id),
            potentials=tuple(values),
        )

    def _entity_pair(
        self,
        left_entity_id: EntityCandidateId,
        right_entity_id: EntityCandidateId,
    ) -> tuple[EntityCandidateId, EntityCandidateId]:
        if left_entity_id <= right_entity_id:
            return (left_entity_id, right_entity_id)
        return (right_entity_id, left_entity_id)

    def _reference_state_id_for_entity(self, entity_id: EntityCandidateId) -> InferenceStateId:
        return InferenceStateId(f"entity:{entity_id}")

    def _unknown_weight(self, scores: tuple[float, ...]) -> float:
        if not scores:
            return 1.0
        return max(0.05, 1.0 - max(scores))

    def _same_event_prior(
        self,
        strategy: FactResolutionStrategy,
    ) -> tuple[float, float]:
        if strategy is FactResolutionStrategy.ENTITY_ALIGNMENT_RELAXED:
            return (0.55, 0.45)
        if strategy is FactResolutionStrategy.SEMANTIC_EVIDENCE:
            return (0.6, 0.4)
        return (0.35, 0.65)

    def _state_depends_on_reference(
        self,
        document: ArticleDocument,
        state,
        reference_id: MentionId,
    ) -> bool:
        match state.filler:
            case EntityFiller(entity_id=entity_id):
                entity = document.store.entity_candidates.get(entity_id)
                return entity is not None and reference_id in entity.reference_ids
            case _:
                return False

    def _reference_role_factor(
        self,
        *,
        role_variable_id: InferenceVariableId,
        role_states: tuple[RoleFillerState, ...],
        reference_id: MentionId,
        reference_variable_id: InferenceVariableId,
        reference_state_ids: tuple[InferenceStateId, ...],
        state_entity_by_state_id: dict[InferenceStateId, EntityCandidateId],
        allowed_entity_kinds: frozenset[EntityKind],
        document: ArticleDocument,
    ) -> InferenceFactor:
        role_entity_ids: frozenset[EntityCandidateId] = frozenset(
            eid for s in role_states for eid in [self._entity_id_from_state(s)] if eid is not None
        )
        values: list[float] = []
        for role_state in role_states:
            depends_on_reference = self._state_depends_on_reference(
                document, role_state, reference_id
            )
            for reference_state_id in reference_state_ids:
                if not depends_on_reference:
                    values.append(1.0)
                elif reference_state_id == UNKNOWN_STATE.id:
                    values.append(0.35)
                else:
                    ref_entity_id = state_entity_by_state_id.get(reference_state_id)
                    if ref_entity_id is None:
                        values.append(1.0)
                        continue
                    ref_entity = document.store.entity_candidates.get(ref_entity_id)
                    if ref_entity is None or ref_entity.kind not in allowed_entity_kinds:
                        values.append(0.02)
                    elif ref_entity_id in role_entity_ids:
                        values.append(0.6)
                    else:
                        values.append(1.0)
        return InferenceFactor(
            id=InferenceFactorId(f"factor:reference-role:{reference_id}:{role_variable_id}"),
            kind=InferenceFactorKind.CONSTRAINT,
            variable_ids=(role_variable_id, reference_variable_id),
            potentials=tuple(values),
        )

    def _entity_id_from_state(self, state: RoleFillerState) -> EntityCandidateId | None:
        match state.filler:
            case EntityFiller(entity_id=eid):
                return eid
            case _:
                return None

    def _normalize(self, weights: tuple[float, ...]) -> tuple[float, ...]:
        total = sum(weights)
        if total <= 0.0:
            return tuple(1.0 / len(weights) for _ in weights)
        return tuple(weight / total for weight in weights)


class ResolutionAssessmentMaterializer:
    producer_id = ProducerId("probabilistic_inference_stage_v2")

    entity_context_threshold = 0.5

    def materialize(
        self,
        *,
        document: ArticleDocument,
        built_graph: BuiltResolutionInferenceGraph,
        result: InferenceResult,
    ) -> ArticleDocument:
        document.store.clear_resolution_claims()
        document.store.clear_reference_resolution_claims()
        document.store.clear_fact_resolution_claims()
        document.store.clear_entity_context_claims()
        for variable_id, proposal in built_graph.entity_proposal_by_variable_id.items():
            marginal = result.marginal_for(variable_id)
            if marginal is None:
                continue
            same_entity_probability = marginal.probability_for(TRUE_STATE.id)
            if same_entity_probability <= 0.5:
                continue
            document.store.add_resolution_claim(
                EntityResolutionClaim(
                    id=document.store.next_resolution_claim_id(),
                    left_entity_id=proposal.left_entity_id,
                    right_entity_id=proposal.right_entity_id,
                    relation=ResolutionRelation.SAME_AS,
                    evidence_ids=proposal.evidence_ids,
                    assessment=self._assessment(
                        score=same_entity_probability,
                        positive=proposal.retrieval_signals,
                        negative=proposal.context_signals,
                        scorer_id=ScorerId("probabilistic_entity_resolution_inference_v2"),
                        explanation="entity resolution posterior from probabilistic inference",
                    ),
                    source=self.producer_id,
                )
            )
        for (
            variable_id,
            state_proposals,
        ) in built_graph.reference_state_proposals_by_variable_id.items():
            marginal = result.marginal_for(variable_id)
            if marginal is None or not state_proposals:
                continue
            unknown_probability = marginal.probability_for(UNKNOWN_STATE.id)
            best_state_id, best_proposal, best_probability = max(
                (
                    (state_id, proposal, marginal.probability_for(state_id))
                    for state_id, proposal in state_proposals.items()
                ),
                key=lambda item: item[2],
            )
            _ = best_state_id
            if best_probability <= unknown_probability:
                continue
            document.store.add_reference_resolution_claim(
                ReferenceResolutionClaim(
                    id=document.store.next_reference_resolution_claim_id(),
                    reference_id=best_proposal.reference_id,
                    candidate_entity_id=best_proposal.candidate_entity_id,
                    relation=ResolutionRelation.REFERENT_OF,
                    evidence_ids=best_proposal.evidence_ids,
                    assessment=self._assessment(
                        score=best_probability,
                        positive=best_proposal.retrieval_signals,
                        negative=best_proposal.context_signals,
                        scorer_id=ScorerId("probabilistic_reference_resolution_inference_v2"),
                        explanation="reference target posterior from probabilistic inference",
                    ),
                    source=self.producer_id,
                )
            )
        for variable_id, proposal in built_graph.same_event_proposal_by_variable_id.items():
            marginal = result.marginal_for(variable_id)
            if marginal is None:
                continue
            probability = marginal.probability_for(TRUE_STATE.id)
            if probability < 0.5:
                continue
            document.store.add_fact_resolution_claim(
                FactResolutionClaim(
                    id=document.store.next_fact_resolution_claim_id(),
                    left_fact_id=proposal.fact_proposal.left_fact_id,
                    right_fact_id=proposal.fact_proposal.right_fact_id,
                    relation=ResolutionRelation.SAME_FACT,
                    evidence_ids=proposal.fact_proposal.evidence_ids,
                    assessment=self._assessment(
                        score=probability,
                        positive=proposal.fact_proposal.retrieval_signals,
                        negative=proposal.fact_proposal.context_signals,
                        scorer_id=ScorerId("probabilistic_fact_resolution_inference_v2"),
                        explanation="same-event posterior from probabilistic inference",
                    ),
                    source=self.producer_id,
                )
            )
        for variable_id, proposal in built_graph.entity_context_proposal_by_variable_id.items():
            marginal = result.marginal_for(variable_id)
            if marginal is None:
                continue
            probability = marginal.probability_for(TRUE_STATE.id)
            if probability < self.entity_context_threshold:
                continue
            document.store.add_entity_context_claim(
                EntityContextClaim(
                    id=document.store.next_entity_context_claim_id(),
                    entity_id=proposal.entity_id,
                    context_kind=proposal.context_kind,
                    evidence_ids=proposal.evidence_ids,
                    assessment=self._assessment(
                        score=probability,
                        positive=proposal.retrieval_signals,
                        negative=(),
                        scorer_id=ScorerId("probabilistic_entity_context_inference_v2"),
                        explanation="entity context posterior from probabilistic inference",
                    ),
                    source=self.producer_id,
                )
            )
        return document

    def _assessment(
        self,
        *,
        score: float,
        positive: tuple[Signal, ...],
        negative: tuple[Signal, ...],
        scorer_id: ScorerId,
        explanation: str,
    ) -> Assessment:
        return Assessment(
            score=round(score, 3),
            positive_signals=tuple(
                signal for signal in positive if signal.polarity is SignalPolarity.POSITIVE
            ),
            negative_signals=tuple(
                signal for signal in negative if signal.polarity is SignalPolarity.NEGATIVE
            ),
            scorer_id=scorer_id,
            explanation=explanation,
        )
