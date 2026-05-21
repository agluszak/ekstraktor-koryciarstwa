from __future__ import annotations

from pipeline_v2.candidates import Assessment, EntityResolutionClaim
from pipeline_v2.document import ArticleDocument
from pipeline_v2.fact_scoring import FactScoringStage
from pipeline_v2.ids import (
    ArgumentBindingCandidateId,
    DocumentId,
    EntityCandidateId,
    EventCandidateId,
    FactCandidateId,
    ProducerId,
    ResolutionClaimId,
    ScorerId,
)
from pipeline_v2.types import (
    AppointmentLemmaSignal,
    EntityKind,
    EventRole,
    FactKind,
    GroundingKind,
    LocalObjectSignal,
    LocalOrganizationSignal,
    LocalPersonSignal,
    LocalRoleSignal,
    LocalSubjectSignal,
    NamedKinshipLemmaSignal,
    ProxyFamilyEntitySignal,
    RelationshipDetail,
    RelationshipDetailSignal,
    ResolutionRelation,
)
from tests_v2.materialized import add_entity, add_event, bind_entity, bind_text, fact_records


def _test_assessment() -> Assessment:
    return Assessment(
        score=0.9,
        positive_signals=(),
        negative_signals=(),
        scorer_id=ScorerId("test-scorer"),
    )


def _document() -> ArticleDocument:
    return ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="",
        paragraphs=(),
    )


def test_probabilistic_inference_emits_same_fact_claim_without_deleting_duplicates() -> None:
    document = _document()
    add_entity(
        document,
        entity_id=EntityCandidateId("person"),
        kind=EntityKind.PERSON,
        canonical_hint="Person",
    )
    add_entity(
        document,
        entity_id=EntityCandidateId("org"),
        kind=EntityKind.ORGANIZATION,
        canonical_hint="Org",
    )
    add_entity(
        document,
        entity_id=EntityCandidateId("role"),
        kind=EntityKind.ROLE,
        canonical_hint="Role",
    )

    first_event_id = EventCandidateId("event-1")
    second_event_id = EventCandidateId("event-2")
    add_event(
        document,
        event_id=first_event_id,
        fact_id=FactCandidateId("fact-1"),
        kind=FactKind.GOVERNANCE_APPOINTMENT,
        signals=(
            AppointmentLemmaSignal(lemma="powołać"),
            LocalPersonSignal(),
            LocalOrganizationSignal(),
            LocalRoleSignal(),
        ),
    )
    add_event(
        document,
        event_id=second_event_id,
        fact_id=FactCandidateId("fact-2"),
        kind=FactKind.GOVERNANCE_APPOINTMENT,
        signals=(
            AppointmentLemmaSignal(lemma="powołać"),
            LocalPersonSignal(),
            LocalOrganizationSignal(),
            LocalRoleSignal(),
        ),
    )
    for event_id, prefix in ((first_event_id, "first"), (second_event_id, "second")):
        bind_entity(
            document,
            binding_id=ArgumentBindingCandidateId(f"{prefix}-person"),
            event_id=event_id,
            role=EventRole.PERSON,
            entity_id=EntityCandidateId("person"),
        )
        bind_entity(
            document,
            binding_id=ArgumentBindingCandidateId(f"{prefix}-org"),
            event_id=event_id,
            role=EventRole.ORGANIZATION,
            entity_id=EntityCandidateId("org"),
        )
        bind_entity(
            document,
            binding_id=ArgumentBindingCandidateId(f"{prefix}-role"),
            event_id=event_id,
            role=EventRole.ROLE,
            entity_id=EntityCandidateId("role"),
        )

    FactScoringStage().run(document)

    claim = next(iter(document.store.fact_resolution_claims.values()))
    assert tuple(record.id for record in fact_records(document)) == ("fact-1", "fact-2")
    assert claim.left_fact_id == FactCandidateId("fact-1")
    assert claim.right_fact_id == FactCandidateId("fact-2")
    assert claim.relation is ResolutionRelation.SAME_FACT
    assert claim.assessment.score >= 0.5


def test_probabilistic_inference_merges_governance_duplicates_when_role_differs_but_org_matches(
) -> None:
    document = _document()
    add_entity(
        document,
        entity_id=EntityCandidateId("person"),
        kind=EntityKind.PERSON,
        canonical_hint="Person",
    )
    add_entity(
        document,
        entity_id=EntityCandidateId("org"),
        kind=EntityKind.ORGANIZATION,
        canonical_hint="Org",
    )
    add_entity(
        document,
        entity_id=EntityCandidateId("role-1"),
        kind=EntityKind.ROLE,
        canonical_hint="Role 1",
    )
    add_entity(
        document,
        entity_id=EntityCandidateId("role-2"),
        kind=EntityKind.ROLE,
        canonical_hint="Role 2",
    )

    first_event_id = EventCandidateId("event-1")
    second_event_id = EventCandidateId("event-2")
    add_event(
        document,
        event_id=first_event_id,
        fact_id=FactCandidateId("fact-1"),
        kind=FactKind.GOVERNANCE_APPOINTMENT,
        signals=(
            AppointmentLemmaSignal(lemma="powołać"),
            LocalPersonSignal(),
            LocalOrganizationSignal(),
            LocalRoleSignal(),
        ),
    )
    add_event(
        document,
        event_id=second_event_id,
        fact_id=FactCandidateId("fact-2"),
        kind=FactKind.GOVERNANCE_APPOINTMENT,
        signals=(
            AppointmentLemmaSignal(lemma="powołać"),
            LocalPersonSignal(),
            LocalOrganizationSignal(),
            LocalRoleSignal(),
        ),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("first-person"),
        event_id=first_event_id,
        role=EventRole.PERSON,
        entity_id=EntityCandidateId("person"),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("first-org"),
        event_id=first_event_id,
        role=EventRole.ORGANIZATION,
        entity_id=EntityCandidateId("org"),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("first-role"),
        event_id=first_event_id,
        role=EventRole.ROLE,
        entity_id=EntityCandidateId("role-1"),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("second-person"),
        event_id=second_event_id,
        role=EventRole.PERSON,
        entity_id=EntityCandidateId("person"),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("second-org"),
        event_id=second_event_id,
        role=EventRole.ORGANIZATION,
        entity_id=EntityCandidateId("org"),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("second-role"),
        event_id=second_event_id,
        role=EventRole.ROLE,
        entity_id=EntityCandidateId("role-2"),
    )

    FactScoringStage().run(document)

    claim = next(iter(document.store.fact_resolution_claims.values()))
    assert claim.left_fact_id == FactCandidateId("fact-1")
    assert claim.right_fact_id == FactCandidateId("fact-2")
    assert claim.relation is ResolutionRelation.SAME_FACT


def test_probabilistic_inference_keeps_governance_facts_separate_without_shared_org() -> None:
    document = _document()
    add_entity(
        document,
        entity_id=EntityCandidateId("person"),
        kind=EntityKind.PERSON,
        canonical_hint="Person",
    )
    add_entity(
        document,
        entity_id=EntityCandidateId("role-1"),
        kind=EntityKind.ROLE,
        canonical_hint="Role 1",
    )
    add_entity(
        document,
        entity_id=EntityCandidateId("role-2"),
        kind=EntityKind.ROLE,
        canonical_hint="Role 2",
    )

    first_event_id = EventCandidateId("event-1")
    second_event_id = EventCandidateId("event-2")
    add_event(
        document,
        event_id=first_event_id,
        fact_id=FactCandidateId("fact-1"),
        kind=FactKind.GOVERNANCE_DISMISSAL,
        signals=(LocalPersonSignal(), LocalRoleSignal()),
    )
    add_event(
        document,
        event_id=second_event_id,
        fact_id=FactCandidateId("fact-2"),
        kind=FactKind.GOVERNANCE_DISMISSAL,
        signals=(LocalPersonSignal(), LocalRoleSignal()),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("first-person"),
        event_id=first_event_id,
        role=EventRole.PERSON,
        entity_id=EntityCandidateId("person"),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("first-role"),
        event_id=first_event_id,
        role=EventRole.ROLE,
        entity_id=EntityCandidateId("role-1"),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("second-person"),
        event_id=second_event_id,
        role=EventRole.PERSON,
        entity_id=EntityCandidateId("person"),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("second-role"),
        event_id=second_event_id,
        role=EventRole.ROLE,
        entity_id=EntityCandidateId("role-2"),
    )

    FactScoringStage().run(document)

    assert document.store.fact_resolution_claims == {}


def test_probabilistic_inference_merges_proxy_and_named_ties_after_same_as_resolution() -> None:
    document = _document()
    add_entity(
        document,
        entity_id=EntityCandidateId("proxy-subject"),
        kind=EntityKind.PERSON,
        canonical_hint="kuzyn of target",
        grounding=GroundingKind.PROXY,
    )
    add_entity(
        document,
        entity_id=EntityCandidateId("named-subject"),
        kind=EntityKind.PERSON,
        canonical_hint="Rafal Dobosz",
    )
    add_entity(
        document,
        entity_id=EntityCandidateId("target"),
        kind=EntityKind.PERSON,
        canonical_hint="Target",
    )

    proxy_event_id = EventCandidateId("event-1")
    named_event_id = EventCandidateId("event-2")
    add_event(
        document,
        event_id=proxy_event_id,
        fact_id=FactCandidateId("fact-1"),
        kind=FactKind.PERSONAL_OR_POLITICAL_TIE,
        signals=(
            NamedKinshipLemmaSignal(lemma="kuzyn"),
            LocalSubjectSignal(),
            LocalObjectSignal(),
            ProxyFamilyEntitySignal(),
        ),
    )
    add_event(
        document,
        event_id=named_event_id,
        fact_id=FactCandidateId("fact-2"),
        kind=FactKind.PERSONAL_OR_POLITICAL_TIE,
        signals=(
            NamedKinshipLemmaSignal(lemma="kuzyn"),
            LocalSubjectSignal(),
            LocalObjectSignal(),
        ),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("proxy-subject"),
        event_id=proxy_event_id,
        role=EventRole.SUBJECT,
        entity_id=EntityCandidateId("proxy-subject"),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("proxy-object"),
        event_id=proxy_event_id,
        role=EventRole.OBJECT,
        entity_id=EntityCandidateId("target"),
    )
    bind_text(
        document,
        binding_id=ArgumentBindingCandidateId("proxy-detail"),
        event_id=proxy_event_id,
        role=EventRole.RELATIONSHIP_DETAIL,
        value="family",
        signals=(RelationshipDetailSignal(detail=RelationshipDetail.FAMILY),),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("named-subject"),
        event_id=named_event_id,
        role=EventRole.SUBJECT,
        entity_id=EntityCandidateId("named-subject"),
    )
    bind_entity(
        document,
        binding_id=ArgumentBindingCandidateId("named-object"),
        event_id=named_event_id,
        role=EventRole.OBJECT,
        entity_id=EntityCandidateId("target"),
    )
    bind_text(
        document,
        binding_id=ArgumentBindingCandidateId("named-detail"),
        event_id=named_event_id,
        role=EventRole.RELATIONSHIP_DETAIL,
        value="family",
        signals=(RelationshipDetailSignal(detail=RelationshipDetail.FAMILY),),
    )
    bind_text(
        document,
        binding_id=ArgumentBindingCandidateId("named-context"),
        event_id=named_event_id,
        role=EventRole.CONTEXT,
        value="kuzyn Rafal Dobosz",
    )
    document.store.add_resolution_claim(
        EntityResolutionClaim(
            id=ResolutionClaimId("resolution-1"),
            left_entity_id=EntityCandidateId("proxy-subject"),
            right_entity_id=EntityCandidateId("named-subject"),
            relation=ResolutionRelation.SAME_AS,
            evidence_ids=(),
            assessment=_test_assessment(),
            source=ProducerId("test"),
        )
    )

    FactScoringStage().run(document)

    claim = next(iter(document.store.fact_resolution_claims.values()))
    assert claim.left_fact_id == FactCandidateId("fact-1")
    assert claim.right_fact_id == FactCandidateId("fact-2")
    assert claim.relation is ResolutionRelation.SAME_FACT
