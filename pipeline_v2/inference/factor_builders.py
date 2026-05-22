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
    EntityCandidateId,
    EventCandidateId,
    EvidenceId,
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
    FactKind,
    GenericOwnerContextSignal,
    GoverningBodyContextSignal,
    GroundingKind,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    PartyOrganizationSignal,
    PossessiveKinshipSignal,
    ProxyFamilyEntitySignal,
    ReferenceKind,
    ReportingSourceContextSignal,
    SelfTieContradictionSignal,
    SemanticEvidenceSimilaritySignal,
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


def resolve_entity_id(store, entity_id: EntityCandidateId) -> EntityCandidateId:
    visited = {entity_id}
    queue = [entity_id]
    all_entities: list[EntityCandidateId] = []

    while queue:
        curr = queue.pop(0)
        all_entities.append(curr)

        # 1. Entity resolution claims (same_as)
        for claim in store.resolution_claims_for_entity(curr):
            other = claim.right_entity_id if claim.left_entity_id == curr else claim.left_entity_id
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


class RoleBaseWeightPolicy:
    def contribution(self, role: EventRole | None, is_unknown: bool) -> float:
        if is_unknown:
            return 0.7
        if role in {EventRole.EMPLOYEE, EventRole.PERSON, EventRole.SUBJECT, EventRole.OBJECT}:
            return 0.1
        if role in {
            EventRole.WORKPLACE,
            EventRole.ORGANIZATION,
            EventRole.FUNDER,
            EventRole.RECIPIENT,
        }:
            return 0.08
        return 0.0


class BindingSignalWeightPolicy:
    def contribution(self, signal: Signal) -> float:
        match signal:
            case LocalPersonSignal() | LocalOrganizationSignal() | LocalRoleSignal():
                return 0.35
            case WindowPersonSignal() | WindowOrganizationSignal() | WindowRoleSignal():
                return 0.15
            case ProxyFamilyEntitySignal() | PossessiveKinshipSignal():
                return 0.35
            case (
                WeakSyntacticBindingSignal()
                | AppointerContextSignal()
                | ControllerContextSignal()
                | PartyOrganizationSignal()
                | ReportingSourceContextSignal()
                | GenericOwnerContextSignal()
                | GoverningBodyContextSignal()
                | SelfTieContradictionSignal()
            ):
                return -0.85
            case _ if signal.polarity is SignalPolarity.POSITIVE:
                return 0.18
            case _:
                return -0.22


class RoleFillerWeightModel:
    def __init__(
        self,
        *,
        base_policy: RoleBaseWeightPolicy | None = None,
        signal_policy: BindingSignalWeightPolicy | None = None,
    ) -> None:
        self.base_policy = base_policy or RoleBaseWeightPolicy()
        self.signal_policy = signal_policy or BindingSignalWeightPolicy()

    def weight(
        self,
        *,
        role: EventRole | None,
        state: RoleFillerState,
        is_unknown: bool,
    ) -> float:
        if is_unknown:
            return self.base_policy.contribution(role, is_unknown=True)
        score = 0.5 + self.base_policy.contribution(role, is_unknown=False)
        for signal in state.signals:
            score += self.signal_policy.contribution(signal)
        return max(0.05, score)


class FactInferenceGraphBuilder:
    semantic_role_threshold = 0.82

    def __init__(
        self,
        prior_registry: FactPriorPolicyRegistry | None = None,
        role_weight_model: RoleFillerWeightModel | None = None,
    ) -> None:
        self.prior_registry = prior_registry or FactPriorPolicyRegistry()
        self.role_weight_model = role_weight_model or RoleFillerWeightModel()

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
            event_variable = self._event_active_variable(event.id, event.kind)
            event_prior = self.prior_registry.prior_for_kind(event.kind, event.signals)
            variables.append(event_variable)
            factors.append(self._event_prior_factor(event.id, event_variable, event_prior, event))
            event_ids_by_variable[event_variable.id] = event.id
            fact_ids_by_variable[event_variable.id] = self._materialized_fact_id(event.id)
            priors_by_variable[event_variable.id] = event_prior

            bindings_by_role: dict[EventRole, list[ArgumentBindingCandidate]] = {}
            for binding in document.store.argument_bindings_for_event(event.id):
                bindings_by_role.setdefault(binding.role, []).append(binding)

            required_roles = {role_spec.role for role_spec in schema.roles if role_spec.required}
            all_roles = required_roles | set(bindings_by_role)
            role_vars = {}
            role_states_map = {}
            for role in sorted(all_roles, key=lambda item: item.value):
                role_spec = schema.role_spec_for(role)
                states = self._role_states(bindings_by_role.get(role, ()))
                role_variable = self._role_variable(event.id, event.kind, role, states)
                variables.append(role_variable)
                role_vars[role] = role_variable
                role_states_map[role] = states
                factors.append(self._role_prior_factor(event.id, role_variable, states))
                if role_spec is not None:
                    factors.append(
                        self._role_compatibility_factor(
                            event_id=event.id,
                            role=role,
                            role_variable=role_variable,
                            role_spec=role_spec,
                            states=states,
                            document=document,
                        )
                    )
                    factors.append(
                        self._event_role_constraint_factor(
                            event_id=event.id,
                            event_variable=event_variable,
                            role_variable=role_variable,
                            required=role_spec.required,
                            state_count=len(states),
                        )
                    )
                    semantic_factor = self._semantic_role_support_factor(
                        document=document,
                        event_id=event.id,
                        role_variable=role_variable,
                        states=states,
                    )
                    if semantic_factor is not None:
                        factors.append(semantic_factor)
                role_variable_id_by_event_role[(event.id, role)] = role_variable.id
                filler_states_by_variable_id[role_variable.id] = states

            if event.kind == FactKind.PERSONAL_OR_POLITICAL_TIE:
                subject_var = role_vars.get(EventRole.SUBJECT)
                object_var = role_vars.get(EventRole.OBJECT)
                if subject_var is not None and object_var is not None:
                    factors.append(
                        self._self_tie_constraint_factor(
                            event_id=event.id,
                            subject_variable=subject_var,
                            subject_states=role_states_map[EventRole.SUBJECT],
                            object_variable=object_var,
                            object_states=role_states_map[EventRole.OBJECT],
                            document=document,
                        )
                    )

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

    def _materialized_fact_id(self, event_id: EventCandidateId) -> FactCandidateId:
        return FactCandidateId(f"materialized:{event_id}")

    def _event_active_variable(self, event_id: EventCandidateId, kind) -> InferenceVariable:
        return InferenceVariable(
            id=InferenceVariableId(f"event-active:{event_id}"),
            kind=InferenceVariableKind.EVENT_ACTIVE,
            states=(FALSE_STATE, TRUE_STATE),
            fact_kind=kind,
        )

    def _event_prior_factor(
        self,
        event_id: EventCandidateId,
        variable: InferenceVariable,
        prior: FactPrior,
        event,
    ) -> InferenceFactor:
        return InferenceFactor(
            id=InferenceFactorId(f"factor:event-prior:{event_id}"),
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
        event_id: EventCandidateId,
        kind,
        role: EventRole,
        states: tuple[RoleFillerState, ...],
    ) -> InferenceVariable:
        return InferenceVariable(
            id=InferenceVariableId(f"role-filler:{event_id}:{role.value}"),
            kind=InferenceVariableKind.ROLE_FILLER,
            states=tuple(state.state for state in states),
            fact_kind=kind,
            role=role,
        )

    def _role_prior_factor(
        self,
        event_key: EventCandidateId,
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
        event_id: EventCandidateId,
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
            id=InferenceFactorId(f"factor:event-role:{event_id}:{role_variable.role}"),
            kind=InferenceFactorKind.CONSTRAINT,
            variable_ids=(event_variable.id, role_variable.id),
            potentials=tuple(values),
        )

    def _role_compatibility_factor(
        self,
        *,
        event_id: EventCandidateId,
        role: EventRole,
        role_variable: InferenceVariable,
        role_spec,
        states: tuple[RoleFillerState, ...],
        document: ArticleDocument,
    ) -> InferenceFactor:
        _ = role
        potentials: list[float] = []
        for state in states:
            is_compatible = True
            match state.filler:
                case EntityFiller(entity_id=entity_id):
                    entity = document.store.entity_candidates.get(entity_id)
                    if entity is None or entity.kind not in role_spec.allowed_entity_kinds:
                        is_compatible = False
                case _:
                    pass

            if is_compatible:
                has_party_signal = self._has_party_organization_signal(state.signals)
                has_reporting_signal = self._has_reporting_source_signal(state.signals)
                has_owner_signal = self._has_owner_context_signal(state.signals)

                if has_party_signal and role_variable.role in {
                    EventRole.WORKPLACE,
                    EventRole.ORGANIZATION,
                    EventRole.FUNDER,
                    EventRole.RECIPIENT,
                    EventRole.COUNTERPARTY,
                    EventRole.HIRING_AUTHORITY,
                }:
                    is_compatible = False
                elif has_reporting_signal and role_variable.role in {
                    EventRole.FUNDER,
                    EventRole.RECIPIENT,
                    EventRole.COUNTERPARTY,
                }:
                    is_compatible = False
                elif has_owner_signal and role_variable.role == EventRole.ORGANIZATION:
                    is_compatible = False

            if is_compatible:
                potentials.append(1.0)
            else:
                potentials.append(0.02)
        return InferenceFactor(
            id=InferenceFactorId(f"factor:role-compatibility:{event_id}:{role_variable.role}"),
            kind=InferenceFactorKind.ROLE_COMPATIBILITY,
            variable_ids=(role_variable.id,),
            potentials=tuple(potentials),
        )

    def _self_tie_constraint_factor(
        self,
        *,
        event_id: EventCandidateId,
        subject_variable: InferenceVariable,
        subject_states: tuple[RoleFillerState, ...],
        object_variable: InferenceVariable,
        object_states: tuple[RoleFillerState, ...],
        document: ArticleDocument,
    ) -> InferenceFactor:
        values: list[float] = []
        for s_state in subject_states:
            for o_state in object_states:
                s_entity_id = None
                o_entity_id = None
                match s_state.filler:
                    case EntityFiller(entity_id=entity_id):
                        s_entity_id = resolve_entity_id(document.store, entity_id)
                    case _:
                        pass
                match o_state.filler:
                    case EntityFiller(entity_id=entity_id):
                        o_entity_id = resolve_entity_id(document.store, entity_id)
                    case _:
                        pass

                if (
                    s_entity_id is not None
                    and o_entity_id is not None
                    and s_entity_id == o_entity_id
                ):
                    values.append(0.000001)
                else:
                    values.append(1.0)
        return InferenceFactor(
            id=InferenceFactorId(f"factor:self-tie:{event_id}"),
            kind=InferenceFactorKind.CONSTRAINT,
            variable_ids=(subject_variable.id, object_variable.id),
            potentials=tuple(values),
        )

    def _semantic_role_support_factor(
        self,
        *,
        document: ArticleDocument,
        event_id: EventCandidateId,
        role_variable: InferenceVariable,
        states: tuple[RoleFillerState, ...],
    ) -> InferenceFactor | None:
        event_evidence_ids = self._event_evidence_ids(document, event_id)
        if not event_evidence_ids:
            return None

        potentials: list[float] = []
        matched_evidence_ids: list[EvidenceId] = []
        matched_signals: list[Signal] = []
        for state in states:
            match state.filler:
                case EntityFiller():
                    match_result = self._semantic_evidence_similarity(
                        document=document,
                        left_evidence_ids=event_evidence_ids,
                        right_evidence_ids=tuple(state.evidence_ids),
                        threshold=self.semantic_role_threshold,
                    )
                case TextFiller():
                    match_result = None
                case _:
                    match_result = None
            if match_result is None:
                potentials.append(1.0)
                continue
            evidence_pair, score = match_result
            potentials.append(1.25)
            matched_evidence_ids.extend(evidence_pair)
            matched_signals.append(SemanticEvidenceSimilaritySignal(score=score))

        if not matched_signals:
            return None
        return InferenceFactor(
            id=InferenceFactorId(f"factor:semantic-role:{event_id}:{role_variable.role}"),
            kind=InferenceFactorKind.EVIDENCE_PRIOR,
            variable_ids=(role_variable.id,),
            potentials=tuple(potentials),
            evidence_ids=tuple(dict.fromkeys(matched_evidence_ids)),
            signals=tuple(dict.fromkeys(matched_signals)),
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
        return tuple(dict.fromkeys(evidence_ids))

    def _semantic_evidence_similarity(
        self,
        *,
        document: ArticleDocument,
        left_evidence_ids: tuple[EvidenceId, ...],
        right_evidence_ids: tuple[EvidenceId, ...],
        threshold: float,
    ) -> tuple[tuple[EvidenceId, EvidenceId], float] | None:
        right_evidence_set = frozenset(right_evidence_ids)
        best: tuple[tuple[EvidenceId, EvidenceId], float] | None = None
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

    def _has_party_organization_signal(self, signals: tuple[Signal, ...]) -> bool:
        for signal in signals:
            match signal:
                case PartyOrganizationSignal():
                    return True
                case _:
                    continue
        return False

    def _has_reporting_source_signal(self, signals: tuple[Signal, ...]) -> bool:
        for signal in signals:
            match signal:
                case ReportingSourceContextSignal():
                    return True
                case _:
                    continue
        return False

    def _has_owner_context_signal(self, signals: tuple[Signal, ...]) -> bool:
        for signal in signals:
            match signal:
                case GenericOwnerContextSignal() | GoverningBodyContextSignal():
                    return True
                case _:
                    continue
        return False

    def _normalized_weights(
        self,
        role: EventRole | None,
        states: tuple[RoleFillerState, ...],
    ) -> tuple[float, ...]:
        if len(states) == 1:
            return (1.0,)
        weights = [
            self.role_weight_model.weight(role=role, state=state, is_unknown=index == 0)
            for index, state in enumerate(states)
        ]
        total = sum(weights)
        return tuple(round(weight / total, 6) for weight in weights)

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
