from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import ArgumentBindingCandidate, EntityFiller, EventCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import (
    ArgumentBindingCandidateId,
    DocumentId,
    EntityCandidateId,
    EventCandidateId,
    EvidenceId,
    FactCandidateId,
    InferenceFactorId,
    InferenceStateId,
    InferenceVariableId,
    ProducerId,
)
from pipeline_v2.inference.backend import InferenceBackend
from pipeline_v2.inference.backends.pgmpy_backend import PgmpyInferenceBackend
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
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.types import EventRole, FactKind


def test_pgmpy_backend_returns_marginal_for_typed_unary_factor() -> None:
    variable = InferenceVariable(
        id=InferenceVariableId("event-active:fact-1"),
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
                id=InferenceFactorId("factor:event-prior:fact-1"),
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
        id=InferenceVariableId("event-active:left"),
        kind=InferenceVariableKind.EVENT_ACTIVE,
        states=(
            InferenceState(InferenceStateId("false"), "false"),
            InferenceState(InferenceStateId("true"), "true"),
        ),
    )
    right_variable = InferenceVariable(
        id=InferenceVariableId("event-active:right"),
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
                id=InferenceFactorId("factor:event-prior:left"),
                kind=InferenceFactorKind.EVIDENCE_PRIOR,
                variable_ids=(left_variable.id,),
                potentials=(0.8, 0.2),
            ),
            InferenceFactor(
                id=InferenceFactorId("factor:event-prior:right"),
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
            source_fact_id=FactCandidateId("fact-1"),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-1"),
            event_id=event_id,
            role=EventRole.SUBJECT,
            filler=EntityFiller(EntityCandidateId("entity-1")),
            evidence_ids=(),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-2"),
            event_id=event_id,
            role=EventRole.OBJECT,
            filler=EntityFiller(EntityCandidateId("entity-2")),
            evidence_ids=(),
        )
    )
    backend = FakeInferenceBackend()

    ProbabilisticInferenceStage(backend=backend).run(document)

    assert backend.observed_spec is not None
    assert len(document.inference_marginals) == 3
    assert any(
        marginal.variable_id == InferenceVariableId("event-active:fact-1")
        for marginal in document.inference_marginals
    )
    assert document.inference_diagnostics == []
    assert len(document.fact_assessments) == 1
    assert document.fact_assessments[0].fact_candidate_id == FactCandidateId("fact-1")
    assert document.fact_assessments[0].assessment.score >= 0.7


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
            source_fact_id=FactCandidateId("fact-1"),
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
