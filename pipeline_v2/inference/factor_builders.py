from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    ArgumentFiller,
    EntityFiller,
    TextFiller,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import (
    EventCandidateId,
    FactCandidateId,
    InferenceFactorId,
    InferenceStateId,
    InferenceVariableId,
)
from pipeline_v2.inference.event_schema import schema_for
from pipeline_v2.inference.fact_priors import FactPrior, FactPriorPolicyRegistry
from pipeline_v2.inference.graph_spec import (
    InferenceFactor,
    InferenceFactorKind,
    InferenceGraphSpec,
    InferenceState,
    InferenceVariable,
    InferenceVariableKind,
)
from pipeline_v2.types import (
    AppointerContextSignal,
    ControllerContextSignal,
    EventRole,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    PartyOrganizationSignal,
    PossessiveKinshipSignal,
    ProxyFamilyEntitySignal,
    Signal,
    SignalPolarity,
    WeakSyntacticBindingSignal,
    WindowOrganizationSignal,
    WindowPersonSignal,
    WindowRoleSignal,
)

TRUE_STATE = InferenceState(InferenceStateId("true"), "true")
FALSE_STATE = InferenceState(InferenceStateId("false"), "false")
UNKNOWN_STATE = InferenceState(InferenceStateId("unknown"), "unknown")


@dataclass(frozen=True, slots=True)
class RoleFillerState:
    state: InferenceState
    filler: ArgumentFiller | None
    evidence_ids: tuple = ()
    signals: tuple[Signal, ...] = ()


@dataclass(frozen=True, slots=True)
class EventInferenceIndex:
    event_id_by_event_variable_id: dict[InferenceVariableId, EventCandidateId]
    fact_id_by_event_variable_id: dict[InferenceVariableId, FactCandidateId]
    prior_by_event_variable_id: dict[InferenceVariableId, FactPrior]
    role_variable_id_by_event_role: dict[tuple[EventCandidateId, EventRole], InferenceVariableId]
    filler_states_by_variable_id: dict[InferenceVariableId, tuple[RoleFillerState, ...]]


@dataclass(frozen=True, slots=True)
class BuiltFactInferenceGraph:
    spec: InferenceGraphSpec
    index: EventInferenceIndex


class FactInferenceGraphBuilder:
    def __init__(self, prior_registry: FactPriorPolicyRegistry | None = None) -> None:
        self.prior_registry = prior_registry or FactPriorPolicyRegistry()

    def build(self, document: ArticleDocument) -> BuiltFactInferenceGraph:
        variables: list[InferenceVariable] = []
        factors: list[InferenceFactor] = []
        event_ids_by_variable: dict[InferenceVariableId, EventCandidateId] = {}
        fact_ids_by_variable: dict[InferenceVariableId, FactCandidateId] = {}
        priors_by_variable: dict[InferenceVariableId, FactPrior] = {}
        role_variable_id_by_event_role: dict[
            tuple[EventCandidateId, EventRole], InferenceVariableId
        ] = {}
        filler_states_by_variable_id: dict[InferenceVariableId, tuple[RoleFillerState, ...]] = {}

        for event in document.store.event_candidates.values():
            schema = schema_for(event.kind)
            event_key = event.source_fact_id or FactCandidateId(str(event.id))
            event_variable = self._event_active_variable(event_key, event.kind)
            event_prior = self.prior_registry.prior_for_kind(event.kind, event.signals)
            variables.append(event_variable)
            factors.append(self._event_prior_factor(event_key, event_variable, event_prior, event))
            event_ids_by_variable[event_variable.id] = event.id
            fact_ids_by_variable[event_variable.id] = event_key
            priors_by_variable[event_variable.id] = event_prior

            bindings_by_role: dict[EventRole, list[ArgumentBindingCandidate]] = {}
            for binding in document.store.argument_bindings_for_event(event.id):
                bindings_by_role.setdefault(binding.role, []).append(binding)

            required_roles = {role_spec.role for role_spec in schema.roles if role_spec.required}
            all_roles = required_roles | set(bindings_by_role)
            for role in sorted(all_roles, key=lambda item: item.value):
                role_spec = schema.role_spec_for(role)
                states = self._role_states(bindings_by_role.get(role, ()))
                role_variable = self._role_variable(event_key, event.kind, role, states)
                variables.append(role_variable)
                factors.append(self._role_prior_factor(event_key, role_variable, states))
                if role_spec is not None:
                    factors.append(
                        self._event_role_constraint_factor(
                            event_key=event_key,
                            event_variable=event_variable,
                            role_variable=role_variable,
                            required=role_spec.required,
                            state_count=len(states),
                        )
                    )
                role_variable_id_by_event_role[(event.id, role)] = role_variable.id
                filler_states_by_variable_id[role_variable.id] = states

        return BuiltFactInferenceGraph(
            spec=InferenceGraphSpec(variables=tuple(variables), factors=tuple(factors)),
            index=EventInferenceIndex(
                event_id_by_event_variable_id=event_ids_by_variable,
                fact_id_by_event_variable_id=fact_ids_by_variable,
                prior_by_event_variable_id=priors_by_variable,
                role_variable_id_by_event_role=role_variable_id_by_event_role,
                filler_states_by_variable_id=filler_states_by_variable_id,
            ),
        )

    def _event_active_variable(self, event_key: FactCandidateId, kind) -> InferenceVariable:
        return InferenceVariable(
            id=InferenceVariableId(f"event-active:{event_key}"),
            kind=InferenceVariableKind.EVENT_ACTIVE,
            states=(FALSE_STATE, TRUE_STATE),
            fact_kind=kind,
        )

    def _event_prior_factor(
        self,
        event_key: FactCandidateId,
        variable: InferenceVariable,
        prior: FactPrior,
        event,
    ) -> InferenceFactor:
        return InferenceFactor(
            id=InferenceFactorId(f"factor:event-prior:{event_key}"),
            kind=InferenceFactorKind.EVIDENCE_PRIOR,
            variable_ids=(variable.id,),
            potentials=(1.0 - prior.score, prior.score),
            evidence_ids=event.evidence_ids,
            signals=event.signals,
        )

    def _role_states(
        self,
        bindings: tuple[ArgumentBindingCandidate, ...] | list[ArgumentBindingCandidate],
    ) -> tuple[RoleFillerState, ...]:
        merged: dict[str, RoleFillerState] = {
            UNKNOWN_STATE.label: RoleFillerState(state=UNKNOWN_STATE, filler=None)
        }
        for binding in bindings:
            filler = binding.filler
            state_id = self._state_id_for_filler(filler)
            existing = merged.get(str(state_id))
            if existing is None:
                merged[str(state_id)] = RoleFillerState(
                    state=InferenceState(state_id, self._state_label_for_filler(filler)),
                    filler=filler,
                    evidence_ids=binding.evidence_ids,
                    signals=binding.signals,
                )
                continue
            merged[str(state_id)] = RoleFillerState(
                state=existing.state,
                filler=existing.filler,
                evidence_ids=tuple(dict.fromkeys([*existing.evidence_ids, *binding.evidence_ids])),
                signals=tuple(dict.fromkeys([*existing.signals, *binding.signals])),
            )
        states = [merged[UNKNOWN_STATE.label]]
        states.extend(merged[key] for key in sorted(merged) if key != UNKNOWN_STATE.label)
        return tuple(states)

    def _role_variable(
        self,
        event_key: FactCandidateId,
        kind,
        role: EventRole,
        states: tuple[RoleFillerState, ...],
    ) -> InferenceVariable:
        return InferenceVariable(
            id=InferenceVariableId(f"role-filler:{event_key}:{role.value}"),
            kind=InferenceVariableKind.ROLE_FILLER,
            states=tuple(state.state for state in states),
            fact_kind=kind,
            role=role,
        )

    def _role_prior_factor(
        self,
        event_key: FactCandidateId,
        variable: InferenceVariable,
        states: tuple[RoleFillerState, ...],
    ) -> InferenceFactor:
        potentials = self._normalized_weights(variable.role, states)
        return InferenceFactor(
            id=InferenceFactorId(f"factor:role-prior:{event_key}:{variable.role}"),
            kind=InferenceFactorKind.ROLE_PRIOR,
            variable_ids=(variable.id,),
            potentials=potentials,
            evidence_ids=tuple(
                dict.fromkeys(evidence_id for state in states for evidence_id in state.evidence_ids)
            ),
            signals=tuple(dict.fromkeys(signal for state in states for signal in state.signals)),
        )

    def _event_role_constraint_factor(
        self,
        *,
        event_key: FactCandidateId,
        event_variable: InferenceVariable,
        role_variable: InferenceVariable,
        required: bool,
        state_count: int,
    ) -> InferenceFactor:
        values: list[float] = []
        for event_state in event_variable.states:
            event_is_true = event_state.id == TRUE_STATE.id
            for index in range(state_count):
                is_unknown = index == 0
                if event_is_true:
                    values.append(0.2 if is_unknown and required else 0.6 if is_unknown else 1.0)
                else:
                    values.append(1.0 if is_unknown else 0.1)
        return InferenceFactor(
            id=InferenceFactorId(f"factor:event-role:{event_key}:{role_variable.role}"),
            kind=InferenceFactorKind.CONSTRAINT,
            variable_ids=(event_variable.id, role_variable.id),
            potentials=tuple(values),
        )

    def _normalized_weights(
        self,
        role: EventRole | None,
        states: tuple[RoleFillerState, ...],
    ) -> tuple[float, ...]:
        if len(states) == 1:
            return (1.0,)
        weights = [
            self._weight_for_state(role, state, index == 0) for index, state in enumerate(states)
        ]
        total = sum(weights)
        return tuple(round(weight / total, 6) for weight in weights)

    def _weight_for_state(
        self,
        role: EventRole | None,
        state: RoleFillerState,
        is_unknown: bool,
    ) -> float:
        if is_unknown:
            return 0.7
        score = 0.5
        if role in {EventRole.EMPLOYEE, EventRole.PERSON, EventRole.SUBJECT, EventRole.OBJECT}:
            score += 0.1
        if role in {
            EventRole.WORKPLACE,
            EventRole.ORGANIZATION,
            EventRole.FUNDER,
            EventRole.RECIPIENT,
        }:
            score += 0.08
        for signal in state.signals:
            match signal:
                case LocalPersonSignal() | LocalOrganizationSignal() | LocalRoleSignal():
                    score += 0.35
                case WindowPersonSignal() | WindowOrganizationSignal() | WindowRoleSignal():
                    score += 0.15
                case ProxyFamilyEntitySignal() | PossessiveKinshipSignal():
                    score += 0.35
                case (
                    WeakSyntacticBindingSignal()
                    | AppointerContextSignal()
                    | ControllerContextSignal()
                    | PartyOrganizationSignal()
                ):
                    score -= 0.85
                case _ if signal.polarity is SignalPolarity.POSITIVE:
                    score += 0.18
                case _:
                    score -= 0.22
        return max(0.05, score)

    def _state_id_for_filler(self, filler: ArgumentFiller) -> InferenceStateId:
        match filler:
            case EntityFiller(entity_id=entity_id):
                return InferenceStateId(f"entity:{entity_id}")
            case TextFiller(value=value):
                return InferenceStateId(f"text:{value.casefold()}")
        raise ValueError(f"unsupported filler for inference state: {filler!r}")

    def _state_label_for_filler(self, filler: ArgumentFiller) -> str:
        match filler:
            case EntityFiller(entity_id=entity_id):
                return str(entity_id)
            case TextFiller(value=value):
                return value
        raise ValueError(f"unsupported filler for inference state: {filler!r}")
