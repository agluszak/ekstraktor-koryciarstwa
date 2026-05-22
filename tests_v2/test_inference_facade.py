from __future__ import annotations

import warnings
from dataclasses import dataclass

import pytest

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    EntityCandidate,
    EntityContextProposal,
    EntityFactArgument,
    EntityFiller,
    EventCandidate,
    ReferenceResolutionProposal,
    TextFiller,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import (
    ArgumentBindingCandidateId,
    DocumentId,
    EntityCandidateId,
    EventCandidateId,
    EvidenceId,
    InferenceFactorId,
    InferenceStateId,
    InferenceVariableId,
    MentionId,
    ProducerId,
    SentenceId,
)
from pipeline_v2.inference.backend import InferenceBackend
from pipeline_v2.inference.backends.pgmpy_backend import PgmpyInferenceBackend
from pipeline_v2.inference.components import InferenceComponentBuilder
from pipeline_v2.inference.factor_builders import TRUE_STATE, FactInferenceGraphBuilder
from pipeline_v2.inference.graph_spec import (
    InferenceFactor,
    InferenceFactorKind,
    InferenceGraphSpec,
    InferenceResult,
    InferenceState,
    InferenceVariable,
    InferenceVariableKind,
    StateProbability,
    VariableMarginal,
)
from pipeline_v2.inference.resolution import ResolutionInferenceGraphBuilder
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.nlp import EvidenceSpan, Mention, ReferenceMention, Sentence, Span
from pipeline_v2.producers import SimpleEntityCandidateProducer
from pipeline_v2.types import (
    CoreferenceProviderLinkSignal,
    EntityKind,
    EntityTag,
    EventRole,
    FactKind,
    FactResolutionStrategy,
    FundingLemmaSignal,
    GroundingKind,
    LocalOrganizationSignal,
    LocalPersonSignal,
    MediaOutletLemmaSignal,
    MentionKind,
    PartyOrganizationSignal,
    PublicContractLemmaSignal,
    PublicEmploymentLemmaSignal,
    PublicInstitutionLemmaSignal,
    ReferenceKind,
    RelationshipDetail,
    ResolutionRelation,
    SemanticEvidenceSimilaritySignal,
)
from tests_v2.materialized import entity_argument


def test_pgmpy_backend_returns_marginal_for_typed_unary_factor() -> None:
    variable = InferenceVariable(
        id=InferenceVariableId("variable-under-test"),
        kind=InferenceVariableKind.EVENT_ACTIVE,
        states=(
            InferenceState(InferenceStateId("false"), "false"),
            InferenceState(InferenceStateId("true"), "true"),
        ),
    )
    spec = InferenceGraphSpec(
        variables=(variable,),
        factors=(
            InferenceFactor(
                id=InferenceFactorId("factor-under-test"),
                kind=InferenceFactorKind.EVIDENCE_PRIOR,
                variable_ids=(variable.id,),
                potentials=(0.2, 0.8),
            ),
        ),
    )

    result = PgmpyInferenceBackend().run(spec)

    marginal = result.marginal_for(variable.id)
    assert marginal is not None
    assert marginal.probability_for(InferenceStateId("true")) == 0.8


def test_pgmpy_backend_runs_disconnected_unary_components_independently() -> None:
    left_variable = InferenceVariable(
        id=InferenceVariableId("left-variable"),
        kind=InferenceVariableKind.EVENT_ACTIVE,
        states=(
            InferenceState(InferenceStateId("false"), "false"),
            InferenceState(InferenceStateId("true"), "true"),
        ),
    )
    right_variable = InferenceVariable(
        id=InferenceVariableId("right-variable"),
        kind=InferenceVariableKind.EVENT_ACTIVE,
        states=(
            InferenceState(InferenceStateId("false"), "false"),
            InferenceState(InferenceStateId("true"), "true"),
        ),
    )
    spec = InferenceGraphSpec(
        variables=(left_variable, right_variable),
        factors=(
            InferenceFactor(
                id=InferenceFactorId("left-factor"),
                kind=InferenceFactorKind.EVIDENCE_PRIOR,
                variable_ids=(left_variable.id,),
                potentials=(0.8, 0.2),
            ),
            InferenceFactor(
                id=InferenceFactorId("right-factor"),
                kind=InferenceFactorKind.EVIDENCE_PRIOR,
                variable_ids=(right_variable.id,),
                potentials=(0.1, 0.9),
            ),
        ),
    )

    result = PgmpyInferenceBackend().run(spec)

    left_marginal = result.marginal_for(left_variable.id)
    right_marginal = result.marginal_for(right_variable.id)
    assert left_marginal is not None
    assert right_marginal is not None
    assert left_marginal.probability_for(InferenceStateId("true")) == 0.2
    assert right_marginal.probability_for(InferenceStateId("true")) == 0.9


def test_pgmpy_backend_returns_uniform_marginal_for_factorless_variable() -> None:
    variable = InferenceVariable(
        id=InferenceVariableId("factorless-variable"),
        kind=InferenceVariableKind.EVENT_ACTIVE,
        states=(
            InferenceState(InferenceStateId("false"), "false"),
            InferenceState(InferenceStateId("true"), "true"),
        ),
    )

    result = PgmpyInferenceBackend().run(InferenceGraphSpec(variables=(variable,), factors=()))

    marginal = result.marginal_for(variable.id)
    assert marginal is not None
    assert marginal.probability_for(InferenceStateId("false")) == 0.5
    assert marginal.probability_for(InferenceStateId("true")) == 0.5


def test_component_builder_groups_connected_variables_and_preserves_factorless_variable() -> None:
    event_variable = InferenceVariable(
        id=InferenceVariableId("event-variable"),
        kind=InferenceVariableKind.EVENT_ACTIVE,
        states=(
            InferenceState(InferenceStateId("event-false"), "false"),
            InferenceState(InferenceStateId("event-true"), "true"),
        ),
    )
    role_variable = InferenceVariable(
        id=InferenceVariableId("role-variable"),
        kind=InferenceVariableKind.ROLE_FILLER,
        states=(
            InferenceState(InferenceStateId("role-unknown"), "unknown"),
            InferenceState(InferenceStateId("role-person"), "person"),
        ),
        role=EventRole.EMPLOYEE,
    )
    independent_variable = InferenceVariable(
        id=InferenceVariableId("independent-variable"),
        kind=InferenceVariableKind.SAME_ENTITY,
        states=(
            InferenceState(InferenceStateId("same-false"), "false"),
            InferenceState(InferenceStateId("same-true"), "true"),
        ),
    )
    connecting_factor = InferenceFactor(
        id=InferenceFactorId("connecting-factor"),
        kind=InferenceFactorKind.CONSTRAINT,
        variable_ids=(event_variable.id, role_variable.id),
        potentials=(1.0, 0.2, 0.2, 1.0),
    )
    spec = InferenceGraphSpec(
        variables=(event_variable, role_variable, independent_variable),
        factors=(connecting_factor,),
    )

    built = InferenceComponentBuilder().build(spec)

    component_variable_sets = {frozenset(component.variable_ids) for component in built.components}
    component_factor_sets = {frozenset(component.factor_ids) for component in built.components}
    rebuilt_variable_ids = {variable.id for variable in built.spec.variables}
    rebuilt_factor_ids = {factor.id for factor in built.spec.factors}
    assert component_variable_sets == {
        frozenset((event_variable.id, role_variable.id)),
        frozenset((independent_variable.id,)),
    }
    assert component_factor_sets == {frozenset((connecting_factor.id,)), frozenset()}
    assert rebuilt_variable_ids == {event_variable.id, role_variable.id, independent_variable.id}
    assert rebuilt_factor_ids == {connecting_factor.id}


def test_component_builder_rejects_factor_referencing_unknown_variable() -> None:
    variable = InferenceVariable(
        id=InferenceVariableId("known-variable"),
        kind=InferenceVariableKind.EVENT_ACTIVE,
        states=(
            InferenceState(InferenceStateId("false"), "false"),
            InferenceState(InferenceStateId("true"), "true"),
        ),
    )
    spec = InferenceGraphSpec(
        variables=(variable,),
        factors=(
            InferenceFactor(
                id=InferenceFactorId("dangling-factor"),
                kind=InferenceFactorKind.CONSTRAINT,
                variable_ids=(variable.id, InferenceVariableId("missing-variable")),
                potentials=(1.0, 1.0, 1.0, 1.0),
            ),
        ),
    )

    with pytest.raises(ValueError, match="unknown variables"):
        InferenceComponentBuilder().build(spec)


def test_pgmpy_backend_sanitizes_zero_potential_factor() -> None:
    variable = InferenceVariable(
        id=InferenceVariableId("zero-potential-variable"),
        kind=InferenceVariableKind.EVENT_ACTIVE,
        states=(
            InferenceState(InferenceStateId("false"), "false"),
            InferenceState(InferenceStateId("true"), "true"),
        ),
    )
    spec = InferenceGraphSpec(
        variables=(variable,),
        factors=(
            InferenceFactor(
                id=InferenceFactorId("zero-potential-factor"),
                kind=InferenceFactorKind.EVIDENCE_PRIOR,
                variable_ids=(variable.id,),
                potentials=(0.0, 0.0),
            ),
        ),
    )

    result = PgmpyInferenceBackend().run(spec)

    marginal = result.marginal_for(variable.id)
    assert marginal is not None
    assert marginal.probability_for(InferenceStateId("false")) == 0.5
    assert marginal.probability_for(InferenceStateId("true")) == 0.5


def test_pgmpy_backend_sanitizes_non_finite_and_negative_potentials() -> None:
    variable = InferenceVariable(
        id=InferenceVariableId("near-zero-variable"),
        kind=InferenceVariableKind.EVENT_ACTIVE,
        states=(
            InferenceState(InferenceStateId("false"), "false"),
            InferenceState(InferenceStateId("true"), "true"),
        ),
    )
    spec = InferenceGraphSpec(
        variables=(variable,),
        factors=(
            InferenceFactor(
                id=InferenceFactorId("near-zero-factor"),
                kind=InferenceFactorKind.EVIDENCE_PRIOR,
                variable_ids=(variable.id,),
                potentials=(float("nan"), -3.0),
            ),
        ),
    )

    result = PgmpyInferenceBackend().run(spec)

    marginal = result.marginal_for(variable.id)
    assert marginal is not None
    assert marginal.probability_for(InferenceStateId("false")) == 0.5
    assert marginal.probability_for(InferenceStateId("true")) == 0.5


def test_pgmpy_backend_infers_connected_role_variable_from_event_support() -> None:
    event_variable = InferenceVariable(
        id=InferenceVariableId("event-variable"),
        kind=InferenceVariableKind.EVENT_ACTIVE,
        states=(
            InferenceState(InferenceStateId("event-false"), "false"),
            InferenceState(InferenceStateId("event-true"), "true"),
        ),
    )
    role_variable = InferenceVariable(
        id=InferenceVariableId("role-variable"),
        kind=InferenceVariableKind.ROLE_FILLER,
        states=(
            InferenceState(InferenceStateId("role-unknown"), "unknown"),
            InferenceState(InferenceStateId("role-person"), "person"),
            InferenceState(InferenceStateId("role-other"), "other"),
        ),
        fact_kind=FactKind.PUBLIC_EMPLOYMENT,
        role=EventRole.EMPLOYEE,
    )
    spec = InferenceGraphSpec(
        variables=(event_variable, role_variable),
        factors=(
            InferenceFactor(
                id=InferenceFactorId("event-prior"),
                kind=InferenceFactorKind.EVIDENCE_PRIOR,
                variable_ids=(event_variable.id,),
                potentials=(0.2, 0.8),
            ),
            InferenceFactor(
                id=InferenceFactorId("role-prior"),
                kind=InferenceFactorKind.ROLE_PRIOR,
                variable_ids=(role_variable.id,),
                potentials=(1.0, 1.0, 1.0),
            ),
            InferenceFactor(
                id=InferenceFactorId("event-role-support"),
                kind=InferenceFactorKind.CONSTRAINT,
                variable_ids=(event_variable.id, role_variable.id),
                potentials=(
                    1.0,
                    0.1,
                    0.1,
                    0.1,
                    5.0,
                    0.1,
                ),
            ),
        ),
    )

    result = PgmpyInferenceBackend().run(spec)

    role_marginal = result.marginal_for(role_variable.id)
    event_marginal = result.marginal_for(event_variable.id)
    assert role_marginal is not None
    assert event_marginal is not None
    assert role_marginal.probability_for(InferenceStateId("role-person")) > (
        role_marginal.probability_for(InferenceStateId("role-unknown"))
    )
    assert event_marginal.probability_for(InferenceStateId("event-true")) > 0.8


def test_pgmpy_backend_rejects_factor_potential_count_mismatch() -> None:
    variable = InferenceVariable(
        id=InferenceVariableId("shape-variable"),
        kind=InferenceVariableKind.EVENT_ACTIVE,
        states=(
            InferenceState(InferenceStateId("false"), "false"),
            InferenceState(InferenceStateId("true"), "true"),
        ),
    )
    spec = InferenceGraphSpec(
        variables=(variable,),
        factors=(
            InferenceFactor(
                id=InferenceFactorId("shape-factor"),
                kind=InferenceFactorKind.EVIDENCE_PRIOR,
                variable_ids=(variable.id,),
                potentials=(1.0,),
            ),
        ),
    )

    with pytest.raises(ValueError, match="expected 2"):
        PgmpyInferenceBackend().run(spec)


def test_pgmpy_backend_suppresses_pgmpy_structure_score_deprecation_warning() -> None:
    variable = InferenceVariable(
        id=InferenceVariableId("warning-variable"),
        kind=InferenceVariableKind.EVENT_ACTIVE,
        states=(
            InferenceState(InferenceStateId("false"), "false"),
            InferenceState(InferenceStateId("true"), "true"),
        ),
    )
    spec = InferenceGraphSpec(
        variables=(variable,),
        factors=(
            InferenceFactor(
                id=InferenceFactorId("warning-factor"),
                kind=InferenceFactorKind.EVIDENCE_PRIOR,
                variable_ids=(variable.id,),
                potentials=(0.2, 0.8),
            ),
        ),
    )

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        PgmpyInferenceBackend().run(spec)

    assert not any("StructureScore" in str(warning.message) for warning in captured)


@dataclass(slots=True)
class FakeInferenceBackend(InferenceBackend):
    observed_spec: InferenceGraphSpec | None = None

    def run(self, spec: InferenceGraphSpec) -> InferenceResult:
        self.observed_spec = spec
        return InferenceResult(
            marginals=tuple(
                VariableMarginal(
                    variable_id=variable.id,
                    probabilities=self._probabilities_for(variable),
                )
                for variable in spec.variables
            )
        )

    def _probabilities_for(
        self,
        variable: InferenceVariable,
    ) -> tuple[StateProbability, ...]:
        if variable.kind is InferenceVariableKind.EVENT_ACTIVE:
            return (
                StateProbability(InferenceStateId("false"), 0.58),
                StateProbability(TRUE_STATE.id, 0.42),
            )
        if variable.kind is InferenceVariableKind.ROLE_FILLER:
            if len(variable.states) == 1:
                return (StateProbability(variable.states[0].id, 1.0),)
            return (
                StateProbability(variable.states[0].id, 0.1),
                StateProbability(variable.states[1].id, 0.9),
                *(StateProbability(state.id, 0.0) for state in variable.states[2:]),
            )
        return tuple(StateProbability(state.id, 0.0) for state in variable.states)


@dataclass(slots=True)
class FakeExternalFactorBuilder:
    def build(
        self,
        *,
        document: ArticleDocument,
        spec: InferenceGraphSpec,
    ) -> tuple[InferenceFactor, ...]:
        _ = document
        event_variable = next(
            variable
            for variable in spec.variables
            if variable.kind is InferenceVariableKind.EVENT_ACTIVE
        )
        return (
            InferenceFactor(
                id=InferenceFactorId("external-support"),
                kind=InferenceFactorKind.EVIDENCE_PRIOR,
                variable_ids=(event_variable.id,),
                potentials=(0.2, 0.8),
            ),
        )


def test_probabilistic_stage_depends_on_backend_facade() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    event_id = EventCandidateId("event-1")
    document.store.add_event_candidate(
        EventCandidate(
            id=event_id,
            kind=FactKind.PARTY_AFFILIATION,
            trigger_evidence_id=None,
            evidence_ids=(),
            source=ProducerId("test"),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-1"),
            event_id=event_id,
            role=EventRole.SUBJECT,
            filler=EntityFiller(EntityCandidateId("subject")),
            evidence_ids=(),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-2"),
            event_id=event_id,
            role=EventRole.OBJECT,
            filler=EntityFiller(EntityCandidateId("object")),
            evidence_ids=(),
        )
    )
    backend = FakeInferenceBackend()

    ProbabilisticInferenceStage(backend=backend).run(document)

    assert backend.observed_spec is not None
    assert len(document.inference_marginals) == 3
    event_variable = next(
        variable
        for variable in backend.observed_spec.variables
        if variable.kind is InferenceVariableKind.EVENT_ACTIVE
    )
    assert any(
        marginal.variable_id == event_variable.id for marginal in document.inference_marginals
    )
    assert document.inference_diagnostics == []
    assert len(document.fact_assessments) == 1
    assert document.fact_assessments[0].materialized_fact_id in {
        record.id for record in document.materialized_fact_records
    }
    assert document.fact_assessments[0].assessment.score >= 0.69


def test_probabilistic_stage_accepts_typed_external_factor_builders() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    document.store.add_event_candidate(
        EventCandidate(
            id=EventCandidateId("event-1"),
            kind=FactKind.PUBLIC_CONTRACT,
            trigger_evidence_id=None,
            evidence_ids=(),
            source=ProducerId("test"),
        )
    )
    backend = FakeInferenceBackend()

    ProbabilisticInferenceStage(
        backend=backend,
        external_factor_builders=(FakeExternalFactorBuilder(),),
    ).run(document)

    assert backend.observed_spec is not None
    assert any(
        factor.id == InferenceFactorId("external-support")
        for factor in backend.observed_spec.factors
    )


def test_fact_graph_builder_maps_public_employment_arguments_to_event_roles() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    event_id = EventCandidateId("event-1")
    document.store.add_event_candidate(
        EventCandidate(
            id=event_id,
            kind=FactKind.PUBLIC_EMPLOYMENT,
            trigger_evidence_id=EvidenceId("evidence-1"),
            evidence_ids=(EvidenceId("evidence-1"),),
            source=ProducerId("test"),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-1"),
            event_id=event_id,
            role=EventRole.EMPLOYEE,
            filler=EntityFiller(EntityCandidateId("person-1")),
            evidence_ids=(EvidenceId("evidence-1"),),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-2"),
            event_id=event_id,
            role=EventRole.WORKPLACE,
            filler=EntityFiller(EntityCandidateId("org-1")),
            evidence_ids=(EvidenceId("evidence-1"),),
        )
    )

    built = FactInferenceGraphBuilder().build(document)

    role_variables = {
        variable.role
        for variable in built.spec.variables
        if variable.kind is InferenceVariableKind.ROLE_FILLER
    }
    assert role_variables == {EventRole.EMPLOYEE, EventRole.WORKPLACE}


def test_fact_graph_builder_penalizes_incompatible_party_workplace_filler() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    event_id = EventCandidateId("event-1")
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("person-1"),
            kind=EntityKind.PERSON,
            mention_ids=(),
            canonical_hint="Jan Kowalski",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("org-1"),
            kind=EntityKind.ORGANIZATION,
            mention_ids=(),
            canonical_hint="Urzad Miasta",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("party-1"),
            kind=EntityKind.POLITICAL_PARTY,
            mention_ids=(),
            canonical_hint="Prawo i Sprawiedliwosc",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_event_candidate(
        EventCandidate(
            id=event_id,
            kind=FactKind.PUBLIC_EMPLOYMENT,
            trigger_evidence_id=None,
            evidence_ids=(),
            source=ProducerId("test"),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-employee"),
            event_id=event_id,
            role=EventRole.EMPLOYEE,
            filler=EntityFiller(EntityCandidateId("person-1")),
            evidence_ids=(),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-workplace-org"),
            event_id=event_id,
            role=EventRole.WORKPLACE,
            filler=EntityFiller(EntityCandidateId("org-1")),
            evidence_ids=(),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-workplace-party"),
            event_id=event_id,
            role=EventRole.WORKPLACE,
            filler=EntityFiller(EntityCandidateId("party-1")),
            evidence_ids=(),
        )
    )

    built = FactInferenceGraphBuilder().build(document)

    workplace_variable = next(
        variable
        for variable in built.spec.variables
        if variable.kind is InferenceVariableKind.ROLE_FILLER
        and variable.role is EventRole.WORKPLACE
    )
    workplace_factor = next(
        factor
        for factor in built.spec.factors
        if factor.kind is InferenceFactorKind.ROLE_COMPATIBILITY
        and factor.variable_ids == (workplace_variable.id,)
    )
    state_by_id = {
        state.state.id: state
        for state in built.index.filler_states_by_variable_id[workplace_variable.id]
    }
    potentials_by_entity_id = {}
    for inference_state, potential in zip(
        workplace_variable.states,
        workplace_factor.potentials,
        strict=True,
    ):
        state = state_by_id.get(inference_state.id)
        if state is None:
            continue
        match state.filler:
            case EntityFiller(entity_id=entity_id):
                potentials_by_entity_id[entity_id] = potential
            case _:
                continue

    assert potentials_by_entity_id[EntityCandidateId("org-1")] == 1.0
    assert potentials_by_entity_id[EntityCandidateId("party-1")] == 0.02


def test_probabilistic_stage_prefers_organization_workplace_over_party_context() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    event_id = EventCandidateId("event-1")
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("person-1"),
            kind=EntityKind.PERSON,
            mention_ids=(),
            canonical_hint="Jan Kowalski",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("org-1"),
            kind=EntityKind.ORGANIZATION,
            mention_ids=(),
            canonical_hint="Urzad Miasta",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("party-1"),
            kind=EntityKind.POLITICAL_PARTY,
            mention_ids=(),
            canonical_hint="Prawo i Sprawiedliwosc",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_event_candidate(
        EventCandidate(
            id=event_id,
            kind=FactKind.PUBLIC_EMPLOYMENT,
            trigger_evidence_id=None,
            evidence_ids=(),
            source=ProducerId("test"),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-employee"),
            event_id=event_id,
            role=EventRole.EMPLOYEE,
            filler=EntityFiller(EntityCandidateId("person-1")),
            evidence_ids=(),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-workplace-org"),
            event_id=event_id,
            role=EventRole.WORKPLACE,
            filler=EntityFiller(EntityCandidateId("org-1")),
            evidence_ids=(),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-workplace-party"),
            event_id=event_id,
            role=EventRole.WORKPLACE,
            filler=EntityFiller(EntityCandidateId("party-1")),
            evidence_ids=(),
        )
    )

    ProbabilisticInferenceStage().run(document)

    primary_record = document.materialized_fact_records[0]
    workplace_argument = entity_argument(primary_record, "organization")
    scores_by_workplace_id = {
        entity_argument(record, "organization"): assessment.assessment.score
        for record in document.materialized_fact_records
        for assessment in document.fact_assessments
        if assessment.materialized_fact_id == record.id
    }

    assert len(document.materialized_fact_records) == 1
    assert workplace_argument == EntityCandidateId("org-1")
    assert EntityCandidateId("party-1") not in scores_by_workplace_id


def test_resolution_graph_adds_reference_role_factor_for_reference_backed_proxy_entity() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    reference_id = MentionId("reference-1")
    event_id = EventCandidateId("event-1")
    document.reference_resolution_proposals.append(
        ReferenceResolutionProposal(
            reference_id=reference_id,
            candidate_entity_id=EntityCandidateId("anchor"),
            evidence_ids=(),
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("anchor"),
            kind=EntityKind.PERSON,
            mention_ids=(),
            canonical_hint="Anchor",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("proxy"),
            kind=EntityKind.PERSON,
            mention_ids=(),
            canonical_hint="Proxy",
            grounding=GroundingKind.PROXY,
            source=ProducerId("test"),
            reference_ids=(reference_id,),
        )
    )
    document.store.add_event_candidate(
        EventCandidate(
            id=event_id,
            kind=FactKind.PERSONAL_OR_POLITICAL_TIE,
            trigger_evidence_id=None,
            evidence_ids=(),
            source=ProducerId("test"),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-subject"),
            event_id=event_id,
            role=EventRole.SUBJECT,
            filler=EntityFiller(EntityCandidateId("proxy")),
            evidence_ids=(),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-object"),
            event_id=event_id,
            role=EventRole.OBJECT,
            filler=EntityFiller(EntityCandidateId("anchor")),
            evidence_ids=(),
        )
    )

    fact_graph = FactInferenceGraphBuilder().build(document)
    built = ResolutionInferenceGraphBuilder().build(document=document, fact_graph=fact_graph)
    subject_variable_id = fact_graph.index.role_variable_id_by_event_role[
        (event_id, EventRole.SUBJECT)
    ]
    reference_variable = next(
        variable
        for variable in built.spec.variables
        if variable.kind is InferenceVariableKind.REFERENCE_TARGET
    )

    assert any(
        factor.kind is InferenceFactorKind.CONSTRAINT
        and factor.variable_ids == (subject_variable_id, reference_variable.id)
        for factor in built.spec.factors
    )


def test_resolution_graph_uses_entity_alignment_strategy_for_same_event_candidates() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Jan Kowalski. Kowalski.",
        paragraphs=("Jan Kowalski. Kowalski.",),
    )
    sentence_id = SentenceId("sentence-1")
    document.store.add_sentence(
        Sentence(
            id=sentence_id,
            sentence_index=0,
            paragraph_index=0,
            text="Jan Kowalski. Kowalski.",
            span=Span(0, len(document.cleaned_text)),
        )
    )
    full_evidence_id = EvidenceId("evidence-full")
    surname_evidence_id = EvidenceId("evidence-surname")
    document.store.add_evidence(
        EvidenceSpan(
            id=full_evidence_id,
            text="Jan Kowalski",
            span=Span(0, 12),
            sentence_id=sentence_id,
            paragraph_index=0,
        )
    )
    document.store.add_evidence(
        EvidenceSpan(
            id=surname_evidence_id,
            text="Kowalski",
            span=Span(14, 22),
            sentence_id=sentence_id,
            paragraph_index=0,
        )
    )
    full_mention = MentionId("mention-full")
    surname_mention = MentionId("mention-surname")
    document.store.add_mention(
        Mention(
            id=full_mention,
            text="Jan Kowalski",
            kind=MentionKind.NER,
            evidence_id=full_evidence_id,
            sentence_id=sentence_id,
        )
    )
    document.store.add_mention(
        Mention(
            id=surname_mention,
            text="Kowalski",
            kind=MentionKind.SURNAME_ONLY,
            evidence_id=surname_evidence_id,
            sentence_id=sentence_id,
            head_lemma="kowalski",
        )
    )
    producer = SimpleEntityCandidateProducer()
    full_person_id = producer.add_full_person(
        document.store,
        candidate_id=EntityCandidateId("person-full"),
        mention_ids=(full_mention,),
        given_name_lemma="jan",
        surname_base="kowalski",
        canonical_hint="Jan Kowalski",
    )
    surname_person_id = producer.add_surname_only_person(
        document.store,
        candidate_id=EntityCandidateId("person-surname"),
        mention_ids=(surname_mention,),
        canonical_hint="Kowalski",
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("org"),
            kind=EntityKind.ORGANIZATION,
            mention_ids=(),
            canonical_hint="Urzad",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    for event_id, employee_id in (
        (EventCandidateId("full-name-event"), full_person_id),
        (EventCandidateId("surname-event"), surname_person_id),
    ):
        document.store.add_event_candidate(
            EventCandidate(
                id=event_id,
                kind=FactKind.PUBLIC_EMPLOYMENT,
                trigger_evidence_id=None,
                evidence_ids=(),
                source=ProducerId("test"),
            )
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=ArgumentBindingCandidateId(f"{event_id}-employee"),
                event_id=event_id,
                role=EventRole.EMPLOYEE,
                filler=EntityFiller(employee_id),
                evidence_ids=(),
            )
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=ArgumentBindingCandidateId(f"{event_id}-workplace"),
                event_id=event_id,
                role=EventRole.WORKPLACE,
                filler=EntityFiller(EntityCandidateId("org")),
                evidence_ids=(),
            )
        )

    fact_graph = FactInferenceGraphBuilder().build(document)
    built = ResolutionInferenceGraphBuilder().build(document=document, fact_graph=fact_graph)

    proposal = next(iter(built.same_event_proposal_by_variable_id.values()))
    assert proposal.strategy.value == "entity_alignment_relaxed"
    assert proposal.linked_entity_pairs == ((full_person_id, surname_person_id),)


def test_semantic_evidence_proposes_same_event_candidate_for_similar_contract_events() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    left_evidence_id = EvidenceId("contract-left")
    right_evidence_id = EvidenceId("contract-right")
    document.store.add_evidence(
        EvidenceSpan(
            id=left_evidence_id,
            text="umowa na obsługę urzędu",
            span=Span(0, 23),
        )
    )
    document.store.add_evidence(
        EvidenceSpan(
            id=right_evidence_id,
            text="kontrakt dotyczący usług dla urzędu",
            span=Span(24, 58),
        )
    )
    document.evidence_index.add(left_evidence_id, (1.0, 0.0))
    document.evidence_index.add(right_evidence_id, (0.95, 0.05))
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("contractor"),
            kind=EntityKind.ORGANIZATION,
            mention_ids=(),
            canonical_hint="Firma",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    for suffix, evidence_id, amount in (
        ("left", left_evidence_id, "100 tys. zł"),
        ("right", right_evidence_id, "120 tys. zł"),
    ):
        event_id = EventCandidateId(f"event-{suffix}")
        document.store.add_event_candidate(
            EventCandidate(
                id=event_id,
                kind=FactKind.PUBLIC_CONTRACT,
                trigger_evidence_id=evidence_id,
                evidence_ids=(evidence_id,),
                source=ProducerId("test"),
                signals=(PublicContractLemmaSignal(lemma="umowa"),),
            )
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=ArgumentBindingCandidateId(f"contractor-{suffix}"),
                event_id=event_id,
                role=EventRole.CONTRACTOR,
                filler=EntityFiller(EntityCandidateId("contractor")),
                evidence_ids=(evidence_id,),
            )
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=ArgumentBindingCandidateId(f"amount-{suffix}"),
                event_id=event_id,
                role=EventRole.AMOUNT,
                filler=TextFiller(amount),
                evidence_ids=(evidence_id,),
            )
        )

    fact_graph = FactInferenceGraphBuilder().build(document)
    resolution_graph = ResolutionInferenceGraphBuilder().build(
        document=document,
        fact_graph=fact_graph,
    )

    semantic_proposals = tuple(
        proposal
        for proposal in resolution_graph.same_event_proposal_by_variable_id.values()
        if proposal.strategy is FactResolutionStrategy.SEMANTIC_EVIDENCE
    )
    assert len(semantic_proposals) == 1
    proposal = semantic_proposals[0]
    assert proposal.fact_proposal.evidence_ids == (left_evidence_id, right_evidence_id)
    assert SemanticEvidenceSimilaritySignal(score=0.998618) in (
        proposal.fact_proposal.retrieval_signals
    )


def test_semantic_evidence_adds_role_filler_support_factor() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    event_evidence_id = EvidenceId("contract-clause")
    filler_evidence_id = EvidenceId("contractor-mention")
    document.store.add_evidence(
        EvidenceSpan(
            id=event_evidence_id,
            text="umowa zawarta z miejską spółką",
            span=Span(0, 30),
        )
    )
    document.store.add_evidence(
        EvidenceSpan(
            id=filler_evidence_id,
            text="miejska spółka jako wykonawca umowy",
            span=Span(31, 67),
        )
    )
    document.evidence_index.add(event_evidence_id, (1.0, 0.0))
    document.evidence_index.add(filler_evidence_id, (0.95, 0.05))
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("contractor"),
            kind=EntityKind.ORGANIZATION,
            mention_ids=(),
            canonical_hint="Miejska spółka",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    event_id = EventCandidateId("contract-event")
    document.store.add_event_candidate(
        EventCandidate(
            id=event_id,
            kind=FactKind.PUBLIC_CONTRACT,
            trigger_evidence_id=event_evidence_id,
            evidence_ids=(event_evidence_id,),
            source=ProducerId("test"),
            signals=(PublicContractLemmaSignal(lemma="umowa"),),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("contractor-binding"),
            event_id=event_id,
            role=EventRole.CONTRACTOR,
            filler=EntityFiller(EntityCandidateId("contractor")),
            evidence_ids=(filler_evidence_id,),
        )
    )

    fact_graph = FactInferenceGraphBuilder().build(document)

    contractor_variable = next(
        variable
        for variable in fact_graph.spec.variables
        if variable.kind is InferenceVariableKind.ROLE_FILLER
        and variable.role is EventRole.CONTRACTOR
    )
    assert any(
        factor.variable_ids == (contractor_variable.id,)
        and SemanticEvidenceSimilaritySignal(score=0.998618) in factor.signals
        for factor in fact_graph.spec.factors
    )


def test_semantic_evidence_adds_reference_target_support_factor() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Ten lokalny polityk podpisał umowę.",
        paragraphs=("Ten lokalny polityk podpisał umowę.",),
    )
    reference_evidence_id = EvidenceId("reference")
    entity_evidence_id = EvidenceId("person")
    reference_id = MentionId("reference")
    mention_id = MentionId("person-mention")
    document.store.add_evidence(
        EvidenceSpan(
            id=reference_evidence_id,
            text="Ten lokalny polityk",
            span=Span(0, 18),
            sentence_id=SentenceId("sentence-1"),
        )
    )
    document.store.add_evidence(
        EvidenceSpan(
            id=entity_evidence_id,
            text="Jan Kowalski, lokalny polityk",
            span=Span(40, 68),
            sentence_id=SentenceId("sentence-1"),
        )
    )
    document.store.add_reference(
        ReferenceMention(
            id=reference_id,
            text="Ten lokalny polityk",
            kind=ReferenceKind.DESCRIPTOR_NOUN_PHRASE,
            evidence_id=reference_evidence_id,
            sentence_id=SentenceId("sentence-1"),
        )
    )
    document.store.add_mention(
        Mention(
            id=mention_id,
            text="Jan Kowalski",
            kind=MentionKind.NER,
            evidence_id=entity_evidence_id,
            sentence_id=SentenceId("sentence-1"),
        )
    )
    document.evidence_index.add(reference_evidence_id, (1.0, 0.0))
    document.evidence_index.add(entity_evidence_id, (0.95, 0.05))
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("person"),
            kind=EntityKind.PERSON,
            mention_ids=(mention_id,),
            canonical_hint="Jan Kowalski",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.reference_resolution_proposals.append(
        ReferenceResolutionProposal(
            reference_id=reference_id,
            candidate_entity_id=EntityCandidateId("person"),
            evidence_ids=(reference_evidence_id, entity_evidence_id),
        )
    )

    resolution_graph = ResolutionInferenceGraphBuilder().build(
        document=document,
        fact_graph=FactInferenceGraphBuilder().build(document),
    )

    reference_variables = {
        variable.id
        for variable in resolution_graph.spec.variables
        if variable.kind is InferenceVariableKind.REFERENCE_TARGET
    }
    assert any(
        set(factor.variable_ids).issubset(reference_variables)
        and SemanticEvidenceSimilaritySignal(score=0.998618) in factor.signals
        for factor in resolution_graph.spec.factors
    )


def test_semantic_evidence_proposes_visible_same_entity_hypothesis_without_name_match() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Jan Kowalski. Burmistrz miasta.",
        paragraphs=("Jan Kowalski. Burmistrz miasta.",),
    )
    first_evidence_id = EvidenceId("named-person")
    second_evidence_id = EvidenceId("descriptor-person")
    first_mention_id = MentionId("named-mention")
    second_mention_id = MentionId("descriptor-mention")
    document.store.add_evidence(
        EvidenceSpan(
            id=first_evidence_id,
            text="Jan Kowalski",
            span=Span(0, 12),
            sentence_id=SentenceId("sentence-1"),
        )
    )
    document.store.add_evidence(
        EvidenceSpan(
            id=second_evidence_id,
            text="Burmistrz miasta",
            span=Span(14, 29),
            sentence_id=SentenceId("sentence-2"),
        )
    )
    document.store.add_mention(
        Mention(
            id=first_mention_id,
            text="Jan Kowalski",
            kind=MentionKind.NER,
            evidence_id=first_evidence_id,
            sentence_id=SentenceId("sentence-1"),
        )
    )
    document.store.add_mention(
        Mention(
            id=second_mention_id,
            text="Burmistrz miasta",
            kind=MentionKind.NER,
            evidence_id=second_evidence_id,
            sentence_id=SentenceId("sentence-2"),
        )
    )
    document.evidence_index.add(first_evidence_id, (1.0, 0.0))
    document.evidence_index.add(second_evidence_id, (0.95, 0.05))
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("named-person"),
            kind=EntityKind.PERSON,
            mention_ids=(first_mention_id,),
            canonical_hint="Jan Kowalski",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("descriptor-person"),
            kind=EntityKind.PERSON,
            mention_ids=(second_mention_id,),
            canonical_hint="Burmistrz miasta",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )

    resolution_graph = ResolutionInferenceGraphBuilder().build(
        document=document,
        fact_graph=FactInferenceGraphBuilder().build(document),
    )

    same_entity_variables = {
        variable.id
        for variable in resolution_graph.spec.variables
        if variable.kind is InferenceVariableKind.SAME_ENTITY
    }
    assert any(
        factor.variable_ids == (variable_id,)
        and SemanticEvidenceSimilaritySignal(score=0.998618) in factor.signals
        for factor in resolution_graph.spec.factors
        for variable_id in same_entity_variables
    )


def _make_proxy_employment_document(
    *,
    reference_signals: tuple,
) -> ArticleDocument:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    reference_id = MentionId("reference-1")
    event_id = EventCandidateId("event-1")
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("anchor-person"),
            kind=EntityKind.PERSON,
            mention_ids=(),
            canonical_hint="Jan Kowalski",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("proxy-person"),
            kind=EntityKind.PERSON,
            mention_ids=(),
            canonical_hint="Kowalski",
            grounding=GroundingKind.PROXY,
            source=ProducerId("test"),
            reference_ids=(reference_id,),
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("org"),
            kind=EntityKind.ORGANIZATION,
            mention_ids=(),
            canonical_hint="Urzad Miasta",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.reference_resolution_proposals.append(
        ReferenceResolutionProposal(
            reference_id=reference_id,
            candidate_entity_id=EntityCandidateId("anchor-person"),
            evidence_ids=(),
            retrieval_signals=reference_signals,
        )
    )
    document.store.add_event_candidate(
        EventCandidate(
            id=event_id,
            kind=FactKind.PUBLIC_EMPLOYMENT,
            trigger_evidence_id=None,
            evidence_ids=(),
            source=ProducerId("test"),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-employee"),
            event_id=event_id,
            role=EventRole.EMPLOYEE,
            filler=EntityFiller(EntityCandidateId("proxy-person")),
            evidence_ids=(),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-workplace"),
            event_id=event_id,
            role=EventRole.WORKPLACE,
            filler=EntityFiller(EntityCandidateId("org")),
            evidence_ids=(),
        )
    )
    return document


def test_stronger_reference_raises_proxy_backed_role_posterior() -> None:
    doc_strong = _make_proxy_employment_document(
        reference_signals=(CoreferenceProviderLinkSignal(),)
    )
    doc_weak = _make_proxy_employment_document(reference_signals=())

    fact_graph = FactInferenceGraphBuilder().build(doc_strong)
    event_id = next(iter(doc_strong.store.event_candidates.keys()))
    employee_variable_id = fact_graph.index.role_variable_id_by_event_role[
        (event_id, EventRole.EMPLOYEE)
    ]
    proxy_state_id = None
    for state in fact_graph.index.filler_states_by_variable_id[employee_variable_id]:
        match state.filler:
            case EntityFiller(entity_id=eid):
                entity = doc_strong.store.entity_candidates.get(eid)
                if entity is not None and entity.grounding is GroundingKind.PROXY:
                    proxy_state_id = state.state.id
    assert proxy_state_id is not None

    ProbabilisticInferenceStage().run(doc_strong)
    ProbabilisticInferenceStage().run(doc_weak)

    strong_marginal = next(
        m for m in doc_strong.inference_marginals if m.variable_id == employee_variable_id
    )
    weak_marginal = next(
        m for m in doc_weak.inference_marginals if m.variable_id == employee_variable_id
    )
    assert strong_marginal.probability_for(proxy_state_id) > weak_marginal.probability_for(
        proxy_state_id
    )


def test_strong_reference_propagates_to_materialized_fact_employee_role() -> None:
    document = _make_proxy_employment_document(reference_signals=(CoreferenceProviderLinkSignal(),))

    ProbabilisticInferenceStage().run(document)

    assert len(document.materialized_fact_records) == 1
    employee_entity = entity_argument(document.materialized_fact_records[0], "person")
    assert employee_entity == EntityCandidateId("anchor-person")


def test_wrong_kind_reference_does_not_raise_proxy_employee_posterior() -> None:
    reference_id = MentionId("reference-1")
    event_id = EventCandidateId("event-1")

    def _make_doc(
        *, org_candidate_signals: tuple, person_candidate_signals: tuple
    ) -> ArticleDocument:
        document = ArticleDocument(
            document_id=DocumentId("doc"),
            source_url=None,
            title="Title",
            publication_date=None,
            cleaned_text="Text.",
            paragraphs=("Text.",),
        )
        document.store.add_entity_candidate(
            EntityCandidate(
                id=EntityCandidateId("anchor-person"),
                kind=EntityKind.PERSON,
                mention_ids=(),
                canonical_hint="Jan Kowalski",
                grounding=GroundingKind.OBSERVED,
                source=ProducerId("test"),
            )
        )
        document.store.add_entity_candidate(
            EntityCandidate(
                id=EntityCandidateId("proxy-person"),
                kind=EntityKind.PERSON,
                mention_ids=(),
                canonical_hint="Kowalski",
                grounding=GroundingKind.PROXY,
                source=ProducerId("test"),
                reference_ids=(reference_id,),
            )
        )
        document.store.add_entity_candidate(
            EntityCandidate(
                id=EntityCandidateId("org"),
                kind=EntityKind.ORGANIZATION,
                mention_ids=(),
                canonical_hint="Urzad Miasta",
                grounding=GroundingKind.OBSERVED,
                source=ProducerId("test"),
            )
        )
        document.reference_resolution_proposals.append(
            ReferenceResolutionProposal(
                reference_id=reference_id,
                candidate_entity_id=EntityCandidateId("anchor-person"),
                evidence_ids=(),
                retrieval_signals=person_candidate_signals,
            )
        )
        document.reference_resolution_proposals.append(
            ReferenceResolutionProposal(
                reference_id=reference_id,
                candidate_entity_id=EntityCandidateId("org"),
                evidence_ids=(),
                retrieval_signals=org_candidate_signals,
            )
        )
        document.store.add_event_candidate(
            EventCandidate(
                id=event_id,
                kind=FactKind.PUBLIC_EMPLOYMENT,
                trigger_evidence_id=None,
                evidence_ids=(),
                source=ProducerId("test"),
                signals=(
                    PublicEmploymentLemmaSignal(lemma="zatrudnić"),
                    LocalPersonSignal(),
                    LocalOrganizationSignal(),
                ),
            )
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=ArgumentBindingCandidateId("binding-employee"),
                event_id=event_id,
                role=EventRole.EMPLOYEE,
                filler=EntityFiller(EntityCandidateId("proxy-person")),
                evidence_ids=(),
            )
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=ArgumentBindingCandidateId("binding-workplace"),
                event_id=event_id,
                role=EventRole.WORKPLACE,
                filler=EntityFiller(EntityCandidateId("org")),
                evidence_ids=(),
            )
        )
        return document

    doc_person_wins = _make_doc(
        person_candidate_signals=(CoreferenceProviderLinkSignal(),),
        org_candidate_signals=(),
    )
    doc_org_wins = _make_doc(
        person_candidate_signals=(),
        org_candidate_signals=(CoreferenceProviderLinkSignal(),),
    )

    fact_graph = FactInferenceGraphBuilder().build(doc_person_wins)
    proxy_state_id = None
    employee_variable_id = fact_graph.index.role_variable_id_by_event_role[
        (event_id, EventRole.EMPLOYEE)
    ]
    for state in fact_graph.index.filler_states_by_variable_id[employee_variable_id]:
        match state.filler:
            case EntityFiller(entity_id=eid):
                entity = doc_person_wins.store.entity_candidates.get(eid)
                if entity is not None and entity.grounding is GroundingKind.PROXY:
                    proxy_state_id = state.state.id

    assert proxy_state_id is not None

    ProbabilisticInferenceStage().run(doc_person_wins)
    ProbabilisticInferenceStage().run(doc_org_wins)

    person_wins_marginal = next(
        m for m in doc_person_wins.inference_marginals if m.variable_id == employee_variable_id
    )
    org_wins_marginal = next(
        m for m in doc_org_wins.inference_marginals if m.variable_id == employee_variable_id
    )
    assert person_wins_marginal.probability_for(proxy_state_id) > org_wins_marginal.probability_for(
        proxy_state_id
    )


def _make_same_surname_document(*, nie_mylic_in_evidence: bool) -> ArticleDocument:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    sentence_id = SentenceId("s1")
    full_evidence_text = (
        "Jan Kowalski, nie mylić z Piotr Kowalski" if nie_mylic_in_evidence else "Jan Kowalski"
    )
    full_evidence_id = EvidenceId("full-evidence")
    surname_evidence_id = EvidenceId("surname-evidence")
    document.store.add_evidence(
        EvidenceSpan(
            id=full_evidence_id,
            text=full_evidence_text,
            span=Span(0, len(full_evidence_text)),
            paragraph_index=0,
        )
    )
    document.store.add_evidence(
        EvidenceSpan(
            id=surname_evidence_id,
            text="Kowalski",
            span=Span(0, 8),
            paragraph_index=0,
        )
    )
    full_mention_id = MentionId("full-mention")
    surname_mention_id = MentionId("surname-mention")
    document.store.add_mention(
        Mention(
            id=full_mention_id,
            text="Jan Kowalski",
            kind=MentionKind.NER,
            evidence_id=full_evidence_id,
            sentence_id=sentence_id,
        )
    )
    document.store.add_mention(
        Mention(
            id=surname_mention_id,
            text="Kowalski",
            kind=MentionKind.SURNAME_ONLY,
            evidence_id=surname_evidence_id,
            sentence_id=sentence_id,
            head_lemma="kowalski",
        )
    )
    producer = SimpleEntityCandidateProducer()
    producer.add_full_person(
        document.store,
        candidate_id=EntityCandidateId("person-full"),
        mention_ids=(full_mention_id,),
        given_name_lemma="jan",
        surname_base="kowalski",
        canonical_hint="Jan Kowalski",
    )
    producer.add_surname_only_person(
        document.store,
        candidate_id=EntityCandidateId("person-surname"),
        mention_ids=(surname_mention_id,),
        canonical_hint="Kowalski",
    )
    return document


def test_same_name_contradiction_lowers_same_entity_posterior() -> None:
    doc_neutral = _make_same_surname_document(nie_mylic_in_evidence=False)
    doc_contradiction = _make_same_surname_document(nie_mylic_in_evidence=True)

    fact_graph = FactInferenceGraphBuilder().build(doc_neutral)
    resolution_graph = ResolutionInferenceGraphBuilder().build(
        document=doc_neutral, fact_graph=fact_graph
    )
    assert len(resolution_graph.entity_proposal_by_variable_id) == 1
    same_entity_variable_id = next(iter(resolution_graph.entity_proposal_by_variable_id.keys()))

    ProbabilisticInferenceStage().run(doc_neutral)
    ProbabilisticInferenceStage().run(doc_contradiction)

    neutral_marginal = next(
        m for m in doc_neutral.inference_marginals if m.variable_id == same_entity_variable_id
    )
    contradiction_marginal = next(
        m for m in doc_contradiction.inference_marginals if m.variable_id == same_entity_variable_id
    )
    assert neutral_marginal.probability_for(TRUE_STATE.id) > contradiction_marginal.probability_for(
        TRUE_STATE.id
    )


def test_nie_mylic_evidence_suppresses_entity_resolution_claim() -> None:
    doc_neutral = _make_same_surname_document(nie_mylic_in_evidence=False)
    ProbabilisticInferenceStage().run(doc_neutral)

    doc_contradiction = _make_same_surname_document(nie_mylic_in_evidence=True)
    ProbabilisticInferenceStage().run(doc_contradiction)

    full_id = EntityCandidateId("person-full")
    surname_id = EntityCandidateId("person-surname")
    assert any(
        {c.left_entity_id, c.right_entity_id} == {full_id, surname_id}
        and c.relation is ResolutionRelation.SAME_AS
        for c in doc_neutral.store.resolution_claims.values()
    )
    assert not any(
        {c.left_entity_id, c.right_entity_id} == {full_id, surname_id}
        for c in doc_contradiction.store.resolution_claims.values()
    )


def _make_duplicate_employment_document(
    *,
    shared_entities: bool,
) -> ArticleDocument:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    person_id = EntityCandidateId("person-1")
    org_id = EntityCandidateId("org-1")
    document.store.add_entity_candidate(
        EntityCandidate(
            id=person_id,
            kind=EntityKind.PERSON,
            mention_ids=(),
            canonical_hint="Jan Kowalski",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=org_id,
            kind=EntityKind.ORGANIZATION,
            mention_ids=(),
            canonical_hint="Urzad",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    if not shared_entities:
        document.store.add_entity_candidate(
            EntityCandidate(
                id=EntityCandidateId("person-2"),
                kind=EntityKind.PERSON,
                mention_ids=(),
                canonical_hint="Jan Kowalski",
                grounding=GroundingKind.OBSERVED,
                source=ProducerId("test"),
            )
        )
    for event_suffix, employee_id in (
        ("event-1", person_id),
        ("event-2", EntityCandidateId("person-2") if not shared_entities else person_id),
    ):
        document.store.add_event_candidate(
            EventCandidate(
                id=EventCandidateId(event_suffix),
                kind=FactKind.PUBLIC_EMPLOYMENT,
                trigger_evidence_id=None,
                evidence_ids=(),
                source=ProducerId("test"),
                signals=(
                    PublicEmploymentLemmaSignal(lemma="zatrudnić"),
                    LocalPersonSignal(),
                    LocalOrganizationSignal(),
                ),
            )
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=ArgumentBindingCandidateId(f"binding-employee-{event_suffix}"),
                event_id=EventCandidateId(event_suffix),
                role=EventRole.EMPLOYEE,
                filler=EntityFiller(employee_id),
                evidence_ids=(),
            )
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=ArgumentBindingCandidateId(f"binding-workplace-{event_suffix}"),
                event_id=EventCandidateId(event_suffix),
                role=EventRole.WORKPLACE,
                filler=EntityFiller(org_id),
                evidence_ids=(),
            )
        )
    return document


def test_exact_argument_match_produces_fact_resolution_claim() -> None:
    document = _make_duplicate_employment_document(shared_entities=True)

    ProbabilisticInferenceStage().run(document)

    assert len(document.store.fact_resolution_claims) == 1
    claim = next(iter(document.store.fact_resolution_claims.values()))
    assert claim.relation is ResolutionRelation.SAME_FACT
    assert claim.assessment.score >= 0.5


def test_exact_argument_match_suppresses_duplicate_materialized_fact() -> None:
    document = _make_duplicate_employment_document(shared_entities=True)

    ProbabilisticInferenceStage().run(document)

    assert len(document.materialized_fact_records) == 1
    record = document.materialized_fact_records[0]
    assert record.kind is FactKind.PUBLIC_EMPLOYMENT
    assert entity_argument(record, "person") == EntityCandidateId("person-1")
    assert entity_argument(record, "organization") == EntityCandidateId("org-1")
    assert record.id in document.materialized_fact_alternatives
    alts = document.materialized_fact_alternatives[record.id]
    assert len(alts) == 1
    assert alts[0].record.kind is FactKind.PUBLIC_EMPLOYMENT


def test_party_organization_workplace_stays_below_primary_materialization_threshold() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    event_id = EventCandidateId("event-1")
    party_id = EntityCandidateId("party-1")
    person_id = EntityCandidateId("person-1")
    document.store.add_entity_candidate(
        EntityCandidate(
            id=party_id,
            kind=EntityKind.POLITICAL_PARTY,
            mention_ids=(),
            canonical_hint="Platforma",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=person_id,
            kind=EntityKind.PERSON,
            mention_ids=(),
            canonical_hint="Jan Kowalski",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_event_candidate(
        EventCandidate(
            id=event_id,
            kind=FactKind.PUBLIC_EMPLOYMENT,
            trigger_evidence_id=None,
            evidence_ids=(),
            source=ProducerId("test"),
            signals=(
                PublicEmploymentLemmaSignal(lemma="zatrudnić"),
                LocalPersonSignal(),
                LocalOrganizationSignal(),
            ),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-employee"),
            event_id=event_id,
            role=EventRole.EMPLOYEE,
            filler=EntityFiller(person_id),
            evidence_ids=(),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-workplace-party"),
            event_id=event_id,
            role=EventRole.WORKPLACE,
            filler=EntityFiller(party_id),
            evidence_ids=(),
            signals=(PartyOrganizationSignal(),),
        )
    )

    ProbabilisticInferenceStage().run(document)

    assert document.materialized_fact_records == []
    assert document.fact_assessments == []


def test_direct_self_tie_stays_below_primary_materialization_threshold() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    event_id = EventCandidateId("event-1")
    person_id = EntityCandidateId("person-1")
    document.store.add_entity_candidate(
        EntityCandidate(
            id=person_id,
            kind=EntityKind.PERSON,
            mention_ids=(),
            canonical_hint="Jan Kowalski",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_event_candidate(
        EventCandidate(
            id=event_id,
            kind=FactKind.PERSONAL_OR_POLITICAL_TIE,
            trigger_evidence_id=None,
            evidence_ids=(),
            source=ProducerId("test"),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-subject"),
            event_id=event_id,
            role=EventRole.SUBJECT,
            filler=EntityFiller(person_id),
            evidence_ids=(),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-object"),
            event_id=event_id,
            role=EventRole.OBJECT,
            filler=EntityFiller(person_id),
            evidence_ids=(),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-detail"),
            event_id=event_id,
            role=EventRole.RELATIONSHIP_DETAIL,
            filler=TextFiller(RelationshipDetail.SPOUSE.value),
            evidence_ids=(),
        )
    )

    ProbabilisticInferenceStage().run(document)

    assert document.materialized_fact_records == []
    assert document.fact_assessments == []


def _setup_funding_event_for_org(
    document: ArticleDocument,
    *,
    event_id: EventCandidateId,
    org_id: EntityCandidateId,
    org_hint: str,
    amount_text: str = "1 mln zł",
) -> None:
    document.store.add_entity_candidate(
        EntityCandidate(
            id=org_id,
            kind=EntityKind.ORGANIZATION,
            mention_ids=(),
            canonical_hint=org_hint,
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_event_candidate(
        EventCandidate(
            id=event_id,
            kind=FactKind.FUNDING,
            trigger_evidence_id=None,
            evidence_ids=(),
            source=ProducerId("test"),
            signals=(
                FundingLemmaSignal(lemma="przyznać"),
                LocalOrganizationSignal(),
            ),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-amount"),
            event_id=event_id,
            role=EventRole.AMOUNT,
            filler=TextFiller(amount_text),
            evidence_ids=(),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-funder"),
            event_id=event_id,
            role=EventRole.FUNDER,
            filler=EntityFiller(org_id),
            evidence_ids=(),
            signals=(LocalOrganizationSignal(),),
        )
    )


def test_media_outlet_entity_context_suppresses_funder_role() -> None:
    """Entity tagged as MEDIA_OUTLET should not surface as a high-confidence FUNDER:
    the EntityContext↔RoleFiller constraint factor suppresses that binding."""
    org_id = EntityCandidateId("pap-org")
    event_id = EventCandidateId("event-funding")
    document = ArticleDocument(
        document_id=DocumentId("doc-media-funder"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    _setup_funding_event_for_org(document, event_id=event_id, org_id=org_id, org_hint="PAP")
    document.entity_context_proposals.append(
        EntityContextProposal(
            entity_id=org_id,
            context_kind=EntityTag.MEDIA_OUTLET,
            evidence_ids=(),
            retrieval_signals=(MediaOutletLemmaSignal(lemma="pap"),),
        )
    )

    ProbabilisticInferenceStage().run(document)

    # The EntityContext claim should be materialized with high posterior.
    media_claims = [
        claim
        for claim in document.store.entity_context_claims.values()
        if claim.entity_id == org_id and claim.context_kind is EntityTag.MEDIA_OUTLET
    ]
    assert len(media_claims) == 1
    assert media_claims[0].assessment.score >= 0.5

    # The funding fact should NOT surface PAP as the high-confidence funder.
    high_confidence_funder_hints = []
    for record in document.materialized_fact_records:
        if record.kind is FactKind.FUNDING:
            assessment = next(
                (a for a in document.fact_assessments if a.materialized_fact_id == record.id),
                None,
            )
            score = assessment.assessment.score if assessment is not None else 0.0
            if score >= 0.5:
                for argument in record.arguments:
                    match argument:
                        case EntityFactArgument(role=argument_role, entity_id=entity_id) if (
                            argument_role.value == "funder"
                        ):
                            hint = document.store.entity_candidates[entity_id].canonical_hint
                            high_confidence_funder_hints.append(hint)
                        case _:
                            continue
    assert "PAP" not in high_confidence_funder_hints


def test_public_institution_entity_context_boosts_workplace_posterior() -> None:
    """The PUBLIC_INSTITUTION tag should boost an organization's posterior in the
    PUBLIC_EMPLOYMENT.WORKPLACE role compared with an otherwise-equivalent untagged
    organization."""

    def run(*, attach_public_institution_proposal: bool) -> float:
        document = ArticleDocument(
            document_id=DocumentId("doc-boost"),
            source_url=None,
            title="Title",
            publication_date=None,
            cleaned_text="Text.",
            paragraphs=("Text.",),
        )
        event_id = EventCandidateId("event-emp")
        person_id = EntityCandidateId("person-emp")
        org_id = EntityCandidateId("ministry-emp")
        document.store.add_entity_candidate(
            EntityCandidate(
                id=person_id,
                kind=EntityKind.PERSON,
                mention_ids=(),
                canonical_hint="Jan Kowalski",
                grounding=GroundingKind.OBSERVED,
                source=ProducerId("test"),
            )
        )
        document.store.add_entity_candidate(
            EntityCandidate(
                id=org_id,
                kind=EntityKind.ORGANIZATION,
                mention_ids=(),
                canonical_hint="Ministerstwo Finansów",
                grounding=GroundingKind.OBSERVED,
                source=ProducerId("test"),
            )
        )
        document.store.add_event_candidate(
            EventCandidate(
                id=event_id,
                kind=FactKind.PUBLIC_EMPLOYMENT,
                trigger_evidence_id=None,
                evidence_ids=(),
                source=ProducerId("test"),
                signals=(
                    PublicEmploymentLemmaSignal(lemma="zatrudnić"),
                    LocalPersonSignal(),
                    LocalOrganizationSignal(),
                ),
            )
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=ArgumentBindingCandidateId("binding-employee"),
                event_id=event_id,
                role=EventRole.EMPLOYEE,
                filler=EntityFiller(person_id),
                evidence_ids=(),
                signals=(LocalPersonSignal(),),
            )
        )
        document.store.add_argument_binding(
            ArgumentBindingCandidate(
                id=ArgumentBindingCandidateId("binding-workplace"),
                event_id=event_id,
                role=EventRole.WORKPLACE,
                filler=EntityFiller(org_id),
                evidence_ids=(),
                signals=(LocalOrganizationSignal(),),
            )
        )
        if attach_public_institution_proposal:
            document.entity_context_proposals.append(
                EntityContextProposal(
                    entity_id=org_id,
                    context_kind=EntityTag.PUBLIC_INSTITUTION,
                    evidence_ids=(),
                    retrieval_signals=(PublicInstitutionLemmaSignal(lemma="ministerstwo"),),
                )
            )

        ProbabilisticInferenceStage().run(document)
        record = next(iter(document.materialized_fact_records), None)
        if record is None:
            return 0.0
        assessment = next(
            (a for a in document.fact_assessments if a.materialized_fact_id == record.id),
            None,
        )
        return assessment.assessment.score if assessment is not None else 0.0

    boosted_score = run(attach_public_institution_proposal=True)
    baseline_score = run(attach_public_institution_proposal=False)

    assert boosted_score >= baseline_score


def test_duplicate_entity_context_proposals_merge_into_one_claim() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc-merged-entity-context"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )
    org_id = EntityCandidateId("entity-ministry")
    document.store.add_entity_candidate(
        EntityCandidate(
            id=org_id,
            kind=EntityKind.ORGANIZATION,
            mention_ids=(),
            canonical_hint="Ministerstwo Finansów",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.entity_context_proposals.extend(
        (
            EntityContextProposal(
                entity_id=org_id,
                context_kind=EntityTag.PUBLIC_INSTITUTION,
                evidence_ids=(EvidenceId("evidence-a"),),
                retrieval_signals=(PublicInstitutionLemmaSignal(lemma="ministerstwo"),),
            ),
            EntityContextProposal(
                entity_id=org_id,
                context_kind=EntityTag.PUBLIC_INSTITUTION,
                evidence_ids=(EvidenceId("evidence-b"),),
                retrieval_signals=(SemanticEvidenceSimilaritySignal(score=0.91),),
            ),
        )
    )

    ProbabilisticInferenceStage().run(document)

    matching_claims = [
        claim
        for claim in document.store.entity_context_claims.values()
        if claim.entity_id == org_id and claim.context_kind is EntityTag.PUBLIC_INSTITUTION
    ]

    assert len(matching_claims) == 1
    claim = matching_claims[0]
    assert claim.evidence_ids == (EvidenceId("evidence-a"), EvidenceId("evidence-b"))
    assert set(claim.assessment.positive_signals) == {
        PublicInstitutionLemmaSignal(lemma="ministerstwo"),
        SemanticEvidenceSimilaritySignal(score=0.91),
    }
