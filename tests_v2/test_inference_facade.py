from __future__ import annotations

from dataclasses import dataclass

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    EntityCandidate,
    EntityFiller,
    EventCandidate,
    ReferenceResolutionProposal,
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
from pipeline_v2.nlp import EvidenceSpan, Mention, Sentence, Span
from pipeline_v2.producers import SimpleEntityCandidateProducer
from pipeline_v2.types import EntityKind, EventRole, FactKind, GroundingKind, MentionKind
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
