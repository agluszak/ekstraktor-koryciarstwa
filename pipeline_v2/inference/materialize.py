from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import (
    Assessment,
    EntityFactArgument,
    EntityFiller,
    FactCandidateRecord,
    TextFactArgument,
    TextFiller,
)
from pipeline_v2.document import ArticleDocument, FactAssessment
from pipeline_v2.ids import EntityCandidateId, EventCandidateId, FactCandidateId, ScorerId
from pipeline_v2.inference.event_schema import RoleSpec, schema_for
from pipeline_v2.inference.factor_builders import (
    TRUE_STATE,
    BuiltFactInferenceGraph,
    RoleFillerState,
)
from pipeline_v2.inference.graph_spec import InferenceResult, VariableMarginal
from pipeline_v2.types import (
    EmploymentContractFormSignal,
    FactArgumentRole,
    GroundingKind,
    ReferenceKind,
    SignalPolarity,
)


@dataclass(frozen=True, slots=True)
class _RoleSelection:
    role_spec: RoleSpec
    state: RoleFillerState
    probability: float


class FactAssessmentMaterializer:
    scorer_id = ScorerId("probabilistic_fact_inference_v2")
    _alternative_threshold = 0.01

    def materialize(
        self,
        *,
        document: ArticleDocument,
        built_graph: BuiltFactInferenceGraph,
        result: InferenceResult,
    ) -> ArticleDocument:
        document.materialized_fact_records = []
        document.fact_assessments = []
        for variable_id, event_id in built_graph.index.event_id_by_event_variable_id.items():
            event_marginal = result.marginal_for(variable_id)
            if event_marginal is None:
                continue
            event_probability = event_marginal.probability_for(TRUE_STATE.id)
            base_fact_id = built_graph.index.fact_id_by_event_variable_id[variable_id]
            for index, (record, score) in enumerate(
                self._materialized_records(
                    document=document,
                    built_graph=built_graph,
                    result=result,
                    event_id=event_id,
                    base_fact_id=base_fact_id,
                    event_probability=event_probability,
                )
            ):
                materialized_id = (
                    base_fact_id if index == 0 else FactCandidateId(f"{base_fact_id}-alt-{index}")
                )
                projected = FactCandidateRecord(
                    id=materialized_id,
                    kind=record.kind,
                    arguments=record.arguments,
                    evidence_ids=record.evidence_ids,
                    source=record.source,
                    signals=record.signals,
                )
                document.materialized_fact_records.append(projected)
                document.fact_assessments.append(
                    FactAssessment(
                        materialized_fact_id=projected.id,
                        assessment=Assessment(
                            score=round(score, 3),
                            positive_signals=tuple(
                                signal
                                for signal in projected.signals
                                if signal.polarity is SignalPolarity.POSITIVE
                            ),
                            negative_signals=tuple(
                                signal
                                for signal in projected.signals
                                if signal.polarity is SignalPolarity.NEGATIVE
                            ),
                            scorer_id=self.scorer_id,
                            explanation="event posterior from typed probabilistic inference graph",
                        ),
                    )
                )
        return document

    def _materialized_records(
        self,
        *,
        document: ArticleDocument,
        built_graph: BuiltFactInferenceGraph,
        result: InferenceResult,
        event_id: EventCandidateId,
        base_fact_id: FactCandidateId,
        event_probability: float,
    ) -> tuple[tuple[FactCandidateRecord, float], ...]:
        event = document.store.event_candidates[event_id]
        schema = schema_for(event.kind)
        selected_by_role: dict[FactArgumentRole, _RoleSelection] = {}
        alternatives: list[tuple[FactArgumentRole, _RoleSelection]] = []
        for role_spec in schema.roles:
            variable_id = built_graph.index.role_variable_id_by_event_role.get(
                (event_id, role_spec.role)
            )
            if variable_id is None:
                if role_spec.required:
                    return ()
                continue
            marginal = result.marginal_for(variable_id)
            states = built_graph.index.filler_states_by_variable_id.get(variable_id, ())
            ranked = self._ranked_states(states, marginal)
            if not ranked:
                if role_spec.required:
                    return ()
                continue
            selected_by_role[role_spec.output_role] = _RoleSelection(role_spec, *ranked[0])
            for state, probability in ranked[1:]:
                if probability >= self._alternative_threshold:
                    alternatives.append(
                        (role_spec.output_role, _RoleSelection(role_spec, state, probability))
                    )

        base_record = self._record_from_selection(
            store=document.store,
            event=event,
            fact_id=base_fact_id,
            selections=tuple(selected_by_role.values()),
        )
        if base_record is None:
            return ()
        materialized: list[tuple[FactCandidateRecord, float]] = [
            (
                base_record,
                self._primary_score(
                    event_probability=event_probability,
                    selections=tuple(selected_by_role.values()),
                ),
            )
        ]
        for role, alternative in alternatives:
            alternative_selection = dict(selected_by_role)
            alternative_selection[role] = alternative
            alternative_record = self._record_from_selection(
                store=document.store,
                event=event,
                fact_id=base_fact_id,
                selections=tuple(alternative_selection.values()),
            )
            if alternative_record is None:
                continue
            materialized.append((alternative_record, event_probability * alternative.probability))
        return tuple(materialized)

    def _primary_score(
        self,
        *,
        event_probability: float,
        selections: tuple[_RoleSelection, ...],
    ) -> float:
        if not selections:
            return event_probability
        mean_role_probability = sum(selection.probability for selection in selections) / len(
            selections
        )
        blended = min(1.0, 0.3 * event_probability + 0.7 * mean_role_probability)
        return blended

    def _resolve_entity_id(self, store, entity_id: EntityCandidateId) -> EntityCandidateId:
        visited = {entity_id}
        queue = [entity_id]
        all_entities: list[EntityCandidateId] = []

        while queue:
            curr = queue.pop(0)
            all_entities.append(curr)

            # 1. Entity resolution claims (same_as)
            for claim in store.resolution_claims_for_entity(curr):
                other = (
                    claim.right_entity_id if claim.left_entity_id == curr else claim.left_entity_id
                )
                if other not in visited:
                    visited.add(other)
                    queue.append(other)

            # 2. Reference resolution claims for proxy entities
            entity_cand = store.entity_candidates.get(curr)
            if entity_cand is not None:
                for ref_id in entity_cand.reference_ids:
                    ref_mention = store.references.get(ref_id)
                    if (
                        ref_mention is not None
                        and ref_mention.kind == ReferenceKind.PROXY_FAMILY_PHRASE
                    ):
                        continue
                    for ref_claim in store.reference_resolution_claims_for_reference(ref_id):
                        target = ref_claim.candidate_entity_id
                        if target not in visited:
                            visited.add(target)
                            queue.append(target)

        # Find the best representative from all_entities
        def candidate_key(ent_id: EntityCandidateId) -> tuple[int, int, int, str]:
            cand = store.entity_candidates.get(ent_id)
            if cand is None:
                return (0, 0, 0, "")

            g_prio = 0
            if cand.grounding == GroundingKind.OBSERVED:
                g_prio = 3
            elif cand.grounding == GroundingKind.INFERRED:
                g_prio = 2
            elif cand.grounding == GroundingKind.PROXY:
                g_prio = 1

            num_mentions = len(cand.mention_ids)
            hint_len = len(cand.canonical_hint) if cand.canonical_hint else 0
            return (g_prio, num_mentions, hint_len, str(ent_id))

        return max(all_entities, key=candidate_key)

    def _record_from_selection(
        self,
        *,
        store,
        event,
        fact_id: FactCandidateId,
        selections: tuple[_RoleSelection, ...],
    ) -> FactCandidateRecord | None:
        arguments = []
        evidence_ids = list(event.evidence_ids)
        signals = list(event.signals)
        for selection in selections:
            evidence_ids.extend(selection.state.evidence_ids)
            signals.extend(selection.state.signals)
            match selection.state.filler:
                case EntityFiller(entity_id=entity_id):
                    resolved_entity_id = self._resolve_entity_id(store, entity_id)
                    arguments.append(
                        EntityFactArgument(selection.role_spec.output_role, resolved_entity_id)
                    )
                case TextFiller(value=value):
                    arguments.append(TextFactArgument(selection.role_spec.output_role, value))
                case None:
                    if selection.role_spec.required:
                        return None
        for signal in event.signals:
            match signal:
                case EmploymentContractFormSignal(form=form):
                    arguments.append(TextFactArgument(FactArgumentRole.CONTEXT, form))
        return FactCandidateRecord(
            id=fact_id,
            kind=event.kind,
            arguments=tuple(arguments),
            evidence_ids=tuple(dict.fromkeys(evidence_ids)),
            source=event.source,
            signals=tuple(dict.fromkeys(signals)),
        )

    def _ranked_states(
        self,
        states: tuple[RoleFillerState, ...],
        marginal: VariableMarginal | None,
    ) -> tuple[tuple[RoleFillerState, float], ...]:
        if marginal is None:
            return ()
        ranked = [
            (state, marginal.probability_for(state.state.id))
            for state in states
            if state.filler is not None
        ]
        ranked.sort(key=lambda item: item[1], reverse=True)
        return tuple(ranked)
