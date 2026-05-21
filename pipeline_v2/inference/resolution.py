from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import (
    Assessment,
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
    FactCandidateId,
    InferenceFactorId,
    InferenceStateId,
    InferenceVariableId,
    MentionId,
    ProducerId,
    ScorerId,
)
from pipeline_v2.inference.event_schema import schema_for
from pipeline_v2.inference.factor_builders import (
    FALSE_STATE,
    TRUE_STATE,
    UNKNOWN_STATE,
    BuiltFactInferenceGraph,
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
from pipeline_v2.scoring import EntityResolutionScorer, ReferenceResolutionScorer
from pipeline_v2.types import (
    DuplicateFactSignal,
    FactArgumentRole,
    FactKind,
    FactResolutionStrategy,
    GroundingKind,
    ResolutionRelation,
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


@dataclass(frozen=True, slots=True)
class _EventBindingView:
    kind: FactKind
    entity_fillers: dict[FactArgumentRole, frozenset[EntityCandidateId]]
    text_fillers: dict[FactArgumentRole, frozenset[str]]
    entity_groundings: dict[FactArgumentRole, tuple[GroundingKind, ...]]


class ResolutionInferenceGraphBuilder:
    producer_id = ProducerId("probabilistic_inference_stage_v2")

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

        same_event_proposal_by_variable_id: dict[InferenceVariableId, SameEventProposal] = {}
        self._add_same_event_variables(
            document=document,
            fact_graph=fact_graph,
            variables=variables,
            factors=factors,
            same_entity_variable_id_by_pair=same_entity_variable_id_by_pair,
            same_event_proposal_by_variable_id=same_event_proposal_by_variable_id,
        )

        return BuiltResolutionInferenceGraph(
            spec=InferenceGraphSpec(variables=tuple(variables), factors=tuple(factors)),
            entity_proposal_by_variable_id=entity_proposal_by_variable_id,
            reference_state_proposals_by_variable_id=reference_state_proposals_by_variable_id,
            same_event_proposal_by_variable_id=same_event_proposal_by_variable_id,
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
        seen_pairs: set[tuple[EntityCandidateId, EntityCandidateId]] = set()
        for entity in document.store.entity_candidates.values():
            for proposal in retriever.proposals_for_entity(entity):
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
                entity_proposal_by_variable_id[variable_id] = enriched
                same_entity_variable_id_by_pair[
                    self._entity_pair(enriched.left_entity_id, enriched.right_entity_id)
                ] = variable_id

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
            for proposal in ordered:
                state_id = self._reference_state_id_for_entity(proposal.candidate_entity_id)
                states.append(InferenceState(state_id, str(proposal.candidate_entity_id)))
                weights.append(scorer.score(proposal).score)
                state_map[state_id] = proposal
                evidence_ids.extend(proposal.evidence_ids)
                signals.extend(proposal.retrieval_signals)
                signals.extend(proposal.context_signals)
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
            reference_state_proposals_by_variable_id[variable_id] = state_map
            reference_variable_id_by_reference_id[ordered[0].reference_id] = variable_id

    def _add_reference_role_factors(
        self,
        *,
        document: ArticleDocument,
        fact_graph: BuiltFactInferenceGraph,
        factors: list[InferenceFactor],
        reference_variable_id_by_reference_id: dict[MentionId, InferenceVariableId],
        reference_state_proposals_by_variable_id: dict[
            InferenceVariableId, dict[InferenceStateId, ReferenceResolutionProposal]
        ]
        | None = None,
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
            for (
                reference_id,
                reference_variable_id,
            ) in reference_variable_id_by_reference_id.items():
                if not any(
                    self._state_depends_on_reference(document, state, reference_id)
                    for state in role_states
                ):
                    continue
                reference_state_ids = (
                    UNKNOWN_STATE.id,
                    *tuple(
                        (reference_state_proposals_by_variable_id or {})
                        .get(reference_variable_id, {})
                        .keys()
                    ),
                )
                factors.append(
                    self._reference_role_factor(
                        role_variable_id=role_variable_id,
                        role_states=role_states,
                        reference_id=reference_id,
                        reference_variable_id=reference_variable_id,
                        reference_state_ids=reference_state_ids,
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
                if strategy is None:
                    continue
                linked_entity_pairs = self._linked_entity_pairs(
                    left, right, strategy, same_entity_variable_id_by_pair
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
                            evidence_ids=(),
                            retrieval_signals=(
                                DuplicateFactSignal(strategy=strategy, fact_kind=left.kind),
                            ),
                        ),
                        linked_entity_pairs=linked_entity_pairs,
                    )
                )
        return tuple(proposals)

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
            if left_object != right_object or left_detail != right_detail or not left_detail:
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
            if left_subject != right_subject and (left_proxy or right_proxy):
                return FactResolutionStrategy.PROXY_NAMED_TIE
            return FactResolutionStrategy.TIE_CONTEXT_RELAXED
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
            left_subjects = tuple(left.entity_fillers.get(FactArgumentRole.SUBJECT, ()))
            right_subjects = tuple(right.entity_fillers.get(FactArgumentRole.SUBJECT, ()))
            if (
                len(left_subjects) == 1
                and len(right_subjects) == 1
                and left_subjects[0] != right_subjects[0]
            ):
                return (self._entity_pair(left_subjects[0], right_subjects[0]),)
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
        role_states,
        reference_id: MentionId,
        reference_variable_id: InferenceVariableId,
        reference_state_ids: tuple[InferenceStateId, ...],
        document: ArticleDocument,
    ) -> InferenceFactor:
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
                    match role_state.filler:
                        case EntityFiller(entity_id=entity_id) if (
                            self._reference_state_id_for_entity(entity_id) == reference_state_id
                        ):
                            values.append(1.0)
                        case _:
                            values.append(0.02)
        return InferenceFactor(
            id=InferenceFactorId(f"factor:reference-role:{reference_id}:{role_variable_id}"),
            kind=InferenceFactorKind.CONSTRAINT,
            variable_ids=(role_variable_id, reference_variable_id),
            potentials=tuple(values),
        )

    def _normalize(self, weights: tuple[float, ...]) -> tuple[float, ...]:
        total = sum(weights)
        if total <= 0.0:
            return tuple(1.0 / len(weights) for _ in weights)
        return tuple(weight / total for weight in weights)


class ResolutionAssessmentMaterializer:
    producer_id = ProducerId("probabilistic_inference_stage_v2")

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
        for variable_id, proposal in built_graph.entity_proposal_by_variable_id.items():
            marginal = result.marginal_for(variable_id)
            if marginal is None:
                continue
            document.store.add_resolution_claim(
                EntityResolutionClaim(
                    id=document.store.next_resolution_claim_id(),
                    left_entity_id=proposal.left_entity_id,
                    right_entity_id=proposal.right_entity_id,
                    relation=ResolutionRelation.SAME_AS,
                    evidence_ids=proposal.evidence_ids,
                    assessment=self._assessment(
                        score=marginal.probability_for(TRUE_STATE.id),
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
