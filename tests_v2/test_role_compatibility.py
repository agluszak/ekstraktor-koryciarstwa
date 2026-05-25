from __future__ import annotations

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    EntityCandidate,
    EntityFiller,
    EventCandidate,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import (
    ArgumentBindingCandidateId,
    DocumentId,
    EntityCandidateId,
    EventCandidateId,
    InferenceStateId,
    ProducerId,
)
from pipeline_v2.inference.factor_builders import FactInferenceGraphBuilder
from pipeline_v2.inference.graph_spec import InferenceFactorKind
from pipeline_v2.types import EntityKind, EventRole, FactKind, GroundingKind


def test_role_compatibility_factor_penalizes_party_in_organization_slot() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )

    # 1. Add Person entity (compatible with EventRole.PERSON)
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

    # 2. Add Organization entity (compatible with EventRole.ORGANIZATION)
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("org-1"),
            kind=EntityKind.ORGANIZATION,
            mention_ids=(),
            canonical_hint="Totalizator Sportowy",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )

    # 3. Add Party entity (incompatible with EventRole.ORGANIZATION)
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("party-1"),
            kind=EntityKind.POLITICAL_PARTY,
            mention_ids=(),
            canonical_hint="PSL",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )

    # 4. Add PUBLIC_ROLE_APPOINTMENT event candidate
    event_id = EventCandidateId("event-1")
    document.store.add_event_candidate(
        EventCandidate(
            id=event_id,
            kind=FactKind.PUBLIC_ROLE_APPOINTMENT,
            trigger_evidence_id=None,
            evidence_ids=(),
            source=ProducerId("test"),
        )
    )

    # 5. Add bindings
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-person"),
            event_id=event_id,
            role=EventRole.PERSON,
            filler=EntityFiller(EntityCandidateId("person-1")),
            evidence_ids=(),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-org"),
            event_id=event_id,
            role=EventRole.ORGANIZATION,
            filler=EntityFiller(EntityCandidateId("org-1")),
            evidence_ids=(),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-party"),
            event_id=event_id,
            role=EventRole.ORGANIZATION,
            filler=EntityFiller(EntityCandidateId("party-1")),
            evidence_ids=(),
        )
    )

    fact_graph = FactInferenceGraphBuilder().build(document)

    variable_id = fact_graph.index.role_variable_id_by_event_role[
        (event_id, EventRole.ORGANIZATION)
    ]
    factor = next(
        f
        for f in fact_graph.spec.factors
        if f.kind is InferenceFactorKind.ROLE_COMPATIBILITY and f.variable_ids == (variable_id,)
    )
    variable = next((v for v in fact_graph.spec.variables if v.id == variable_id), None)
    assert variable is not None

    state_ids = [state.id for state in variable.states]
    assert state_ids[0] == "unknown"
    assert "entity:org-1" in state_ids
    assert "entity:party-1" in state_ids

    org_index = state_ids.index(InferenceStateId("entity:org-1"))
    party_index = state_ids.index(InferenceStateId("entity:party-1"))

    assert factor.potentials[0] == 1.0  # UNKNOWN is allowed (1.0)
    assert factor.potentials[org_index] == 1.0
    assert factor.potentials[party_index] == 0.02
