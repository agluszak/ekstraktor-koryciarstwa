from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import (
    Assessment,
    EntityFactArgument,
    EntityFiller,
    FactArgument,
    FactCandidateRecord,
    MaterializedFactAlternative,
    MaterializedRoleAlternative,
    TextFactArgument,
    TextFiller,
)
from pipeline_v2.document import ArticleDocument, FactAssessment
from pipeline_v2.ids import EventCandidateId, FactCandidateId, ResolutionClaimId, ScorerId
from pipeline_v2.inference.event_schema import RoleSpec, schema_for
from pipeline_v2.inference.factor_builders import (
    TRUE_STATE,
    BuiltFactInferenceGraph,
    RoleFillerState,
    resolve_entity_id,
)
from pipeline_v2.inference.graph_spec import InferenceResult, VariableMarginal
from pipeline_v2.types import (
    EmploymentContractFormSignal,
    FactArgumentRole,
    FactKind,
    ResolutionRelation,
    SelfTieContradictionSignal,
    SignalPolarity,
)


@dataclass(frozen=True, slots=True)
class _RoleSelection:
    role_spec: RoleSpec
    state: RoleFillerState
    probability: float


@dataclass(frozen=True, slots=True)
class _FactProjection:
    primary_id: FactCandidateId
    alternative_ids: tuple[FactCandidateId, ...]
    claim_id: ResolutionClaimId
    relation: ResolutionRelation


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
        document.materialized_role_alternatives = {}
        document.materialized_fact_alternatives = {}
        document.fact_assessments = []

        records: dict[FactCandidateId, FactCandidateRecord] = {}
        scores: dict[FactCandidateId, float] = {}
        alternatives_map: dict[FactCandidateId, tuple[MaterializedRoleAlternative, ...]] = {}

        for variable_id, event_id in built_graph.index.event_id_by_event_variable_id.items():
            event_marginal = result.marginal_for(variable_id)
            if event_marginal is None:
                continue
            event_probability = event_marginal.probability_for(TRUE_STATE.id)
            base_fact_id = built_graph.index.fact_id_by_event_variable_id[variable_id]
            materialized = self._materialized_record(
                document=document,
                built_graph=built_graph,
                result=result,
                event_id=event_id,
                base_fact_id=base_fact_id,
                event_probability=event_probability,
            )
            if materialized is None:
                continue
            record, score, alts = materialized
            records[base_fact_id] = record
            scores[base_fact_id] = score
            alternatives_map[base_fact_id] = alts

        projections = self._fact_projection_groups(document, scores)
        suppressed_ids = frozenset(
            alt_id for proj in projections for alt_id in proj.alternative_ids
        )
        projection_by_suppressed = {
            alt_id: proj for proj in projections for alt_id in proj.alternative_ids
        }

        for fact_id, record in records.items():
            if fact_id in suppressed_ids:
                proj = projection_by_suppressed[fact_id]
                existing = document.materialized_fact_alternatives.get(proj.primary_id, ())
                document.materialized_fact_alternatives[proj.primary_id] = (
                    *existing,
                    MaterializedFactAlternative(
                        record=record,
                        score=round(scores[fact_id], 3),
                        claim_id=proj.claim_id,
                        relation=proj.relation,
                    ),
                )
                continue
            score = scores[fact_id]
            alts = alternatives_map[fact_id]
            document.materialized_fact_records.append(record)
            if alts:
                document.materialized_role_alternatives[record.id] = alts
            document.fact_assessments.append(
                FactAssessment(
                    materialized_fact_id=record.id,
                    assessment=Assessment(
                        score=round(score, 3),
                        positive_signals=tuple(
                            signal
                            for signal in record.signals
                            if signal.polarity is SignalPolarity.POSITIVE
                        ),
                        negative_signals=tuple(
                            signal
                            for signal in record.signals
                            if signal.polarity is SignalPolarity.NEGATIVE
                        ),
                        scorer_id=self.scorer_id,
                        explanation=(
                            "event posterior and role posteriors from typed probabilistic "
                            "inference graph"
                        ),
                    ),
                )
            )
        return document

    def _fact_projection_groups(
        self,
        document: ArticleDocument,
        scores: dict[FactCandidateId, float],
    ) -> tuple[_FactProjection, ...]:
        projections: list[_FactProjection] = []
        for claim in document.store.fact_resolution_claims.values():
            left, right = claim.left_fact_id, claim.right_fact_id
            left_score = scores.get(left)
            right_score = scores.get(right)
            if left_score is None or right_score is None:
                continue
            if left_score >= right_score:
                projections.append(
                    _FactProjection(
                        primary_id=left,
                        alternative_ids=(right,),
                        claim_id=claim.id,
                        relation=claim.relation,
                    )
                )
            else:
                projections.append(
                    _FactProjection(
                        primary_id=right,
                        alternative_ids=(left,),
                        claim_id=claim.id,
                        relation=claim.relation,
                    )
                )
        return tuple(projections)

    def _materialized_record(
        self,
        *,
        document: ArticleDocument,
        built_graph: BuiltFactInferenceGraph,
        result: InferenceResult,
        event_id: EventCandidateId,
        base_fact_id: FactCandidateId,
        event_probability: float,
    ) -> tuple[FactCandidateRecord, float, tuple[MaterializedRoleAlternative, ...]] | None:
        event = document.store.event_candidates[event_id]
        schema = schema_for(event.kind)
        selected_by_role: dict[FactArgumentRole, _RoleSelection] = {}
        alternatives: list[MaterializedRoleAlternative] = []
        for role_spec in schema.roles:
            variable_id = built_graph.index.role_variable_id_by_event_role.get(
                (event_id, role_spec.role)
            )
            if variable_id is None:
                if role_spec.required:
                    return None
                continue
            marginal = result.marginal_for(variable_id)
            states = built_graph.index.filler_states_by_variable_id.get(variable_id, ())
            ranked = self._ranked_states(states, marginal)
            if not ranked:
                if role_spec.required:
                    return None
                continue
            selected_by_role[role_spec.output_role] = _RoleSelection(role_spec, *ranked[0])
            for state, probability in ranked[1:]:
                if probability < self._alternative_threshold:
                    continue
                filler = self._fact_argument_from_state(
                    store=document.store,
                    output_role=role_spec.output_role,
                    state=state,
                )
                if filler is None:
                    continue
                alternatives.append(
                    MaterializedRoleAlternative(
                        role=role_spec.output_role,
                        filler=filler,
                        posterior=round(probability, 6),
                        evidence_ids=state.evidence_ids,
                        signals=state.signals,
                    )
                )

        selections = tuple(selected_by_role.values())
        base_record = self._record_from_selection(
            store=document.store,
            event=event,
            fact_id=base_fact_id,
            selections=selections,
        )
        if base_record is None:
            return None
        score = self._primary_score(
            event_probability=event_probability,
            selections=selections,
        )
        return base_record, score, tuple(alternatives)

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
        return min(1.0, 0.3 * event_probability + 0.7 * mean_role_probability)

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
                    resolved_entity_id = resolve_entity_id(store, entity_id)
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
        if event.kind is FactKind.PERSONAL_OR_POLITICAL_TIE and self._is_self_tie(arguments):
            signals.append(
                SelfTieContradictionSignal(
                    reason="subject and object resolve to the same entity representative"
                )
            )
        return FactCandidateRecord(
            id=fact_id,
            kind=event.kind,
            arguments=tuple(arguments),
            evidence_ids=tuple(dict.fromkeys(evidence_ids)),
            source=event.source,
            signals=tuple(dict.fromkeys(signals)),
        )

    def _fact_argument_from_state(
        self,
        *,
        store,
        output_role: FactArgumentRole,
        state: RoleFillerState,
    ) -> FactArgument | None:
        match state.filler:
            case EntityFiller(entity_id=entity_id):
                return EntityFactArgument(output_role, resolve_entity_id(store, entity_id))
            case TextFiller(value=value):
                return TextFactArgument(output_role, value)
            case None:
                return None

    def _is_self_tie(self, arguments: list[FactArgument]) -> bool:
        subject_id = None
        object_id = None
        for argument in arguments:
            match argument:
                case EntityFactArgument(role=FactArgumentRole.SUBJECT, entity_id=entity_id):
                    subject_id = entity_id
                case EntityFactArgument(role=FactArgumentRole.OBJECT, entity_id=entity_id):
                    object_id = entity_id
                case _:
                    continue
        return subject_id is not None and subject_id == object_id

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
