from __future__ import annotations

from pipeline_v2.candidates import (
    Assessment,
    EntityCandidate,
    EntityResolutionClaim,
    GovernanceFactCandidate,
    PersonalTieFactCandidate,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.fact_resolution import FactResolutionStage
from pipeline_v2.ids import (
    DocumentId,
    EntityCandidateId,
    EvidenceId,
    FactCandidateId,
    ProducerId,
    ResolutionClaimId,
    ScorerId,
)
from pipeline_v2.types import (
    EntityKind,
    FactKind,
    GroundingKind,
    RelationshipDetail,
    ResolutionRelation,
)


def _test_assessment() -> Assessment:
    return Assessment(
        score=0.9,
        positive_signals=(),
        negative_signals=(),
        scorer_id=ScorerId("test-scorer"),
    )


def test_fact_resolution_stage_emits_same_fact_claim_without_deleting_duplicates() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="",
        paragraphs=(),
    )
    first = GovernanceFactCandidate(
        id=FactCandidateId("fact-1"),
        kind=FactKind.GOVERNANCE_APPOINTMENT,
        person_entity_id=EntityCandidateId("person"),
        organization_entity_id=EntityCandidateId("org"),
        role_entity_id=EntityCandidateId("role"),
        evidence_ids=(),
        source=ProducerId("test"),
    )
    duplicate = GovernanceFactCandidate(
        id=FactCandidateId("fact-2"),
        kind=FactKind.GOVERNANCE_APPOINTMENT,
        person_entity_id=EntityCandidateId("person"),
        organization_entity_id=EntityCandidateId("org"),
        role_entity_id=EntityCandidateId("role"),
        evidence_ids=(),
        source=ProducerId("test"),
    )
    document.store.add_fact_candidate(first)
    document.store.add_fact_candidate(duplicate)

    FactResolutionStage().run(document)

    claim = next(iter(document.store.fact_resolution_claims.values()))
    assert tuple(document.store.fact_candidates) == ("fact-1", "fact-2")
    assert claim.left_fact_id == first.id
    assert claim.right_fact_id == duplicate.id
    assert claim.relation is ResolutionRelation.SAME_FACT
    assert claim.assessment.score >= 0.8


def test_fact_resolution_stage_merges_governance_duplicates_when_role_differs_but_org_matches() -> (
    None
):
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="",
        paragraphs=(),
    )
    first = GovernanceFactCandidate(
        id=FactCandidateId("fact-1"),
        kind=FactKind.GOVERNANCE_APPOINTMENT,
        person_entity_id=EntityCandidateId("person"),
        organization_entity_id=EntityCandidateId("org"),
        role_entity_id=EntityCandidateId("role-1"),
        evidence_ids=(),
        source=ProducerId("test"),
    )
    duplicate = GovernanceFactCandidate(
        id=FactCandidateId("fact-2"),
        kind=FactKind.GOVERNANCE_APPOINTMENT,
        person_entity_id=EntityCandidateId("person"),
        organization_entity_id=EntityCandidateId("org"),
        role_entity_id=EntityCandidateId("role-2"),
        evidence_ids=(),
        source=ProducerId("test"),
    )
    document.store.add_fact_candidate(first)
    document.store.add_fact_candidate(duplicate)

    FactResolutionStage().run(document)

    claim = next(iter(document.store.fact_resolution_claims.values()))
    assert claim.left_fact_id == first.id
    assert claim.right_fact_id == duplicate.id
    assert claim.relation is ResolutionRelation.SAME_FACT


def test_fact_resolution_stage_keeps_governance_facts_separate_without_shared_org() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="",
        paragraphs=(),
    )
    first = GovernanceFactCandidate(
        id=FactCandidateId("fact-1"),
        kind=FactKind.GOVERNANCE_DISMISSAL,
        person_entity_id=EntityCandidateId("person"),
        organization_entity_id=None,
        role_entity_id=EntityCandidateId("role-1"),
        evidence_ids=(),
        source=ProducerId("test"),
    )
    other = GovernanceFactCandidate(
        id=FactCandidateId("fact-2"),
        kind=FactKind.GOVERNANCE_DISMISSAL,
        person_entity_id=EntityCandidateId("person"),
        organization_entity_id=None,
        role_entity_id=EntityCandidateId("role-2"),
        evidence_ids=(),
        source=ProducerId("test"),
    )
    document.store.add_fact_candidate(first)
    document.store.add_fact_candidate(other)

    FactResolutionStage().run(document)

    assert document.store.fact_resolution_claims == {}


def test_fact_resolution_stage_merges_proxy_and_named_ties_after_same_as_resolution() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="",
        paragraphs=(),
    )
    proxy_tie = PersonalTieFactCandidate(
        id=FactCandidateId("fact-1"),
        subject_entity_id=EntityCandidateId("proxy-subject"),
        object_entity_id=EntityCandidateId("target"),
        evidence_ids=(EvidenceId("evidence-1"),),
        source=ProducerId("test"),
        relationship_detail=RelationshipDetail.FAMILY,
    )
    named_tie = PersonalTieFactCandidate(
        id=FactCandidateId("fact-2"),
        subject_entity_id=EntityCandidateId("named-subject"),
        object_entity_id=EntityCandidateId("target"),
        evidence_ids=(EvidenceId("evidence-2"),),
        source=ProducerId("test"),
        relationship_detail=RelationshipDetail.FAMILY,
        context_text="kuzyn Rafał Dobosz",
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("proxy-subject"),
            kind=EntityKind.PERSON,
            mention_ids=(),
            canonical_hint="kuzyn of target",
            grounding=GroundingKind.PROXY,
            source=ProducerId("test"),
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("named-subject"),
            kind=EntityKind.PERSON,
            mention_ids=(),
            canonical_hint="Rafal Dobosz",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("target"),
            kind=EntityKind.PERSON,
            mention_ids=(),
            canonical_hint="Target",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    document.store.add_fact_candidate(proxy_tie)
    document.store.add_fact_candidate(named_tie)
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

    FactResolutionStage().run(document)

    claim = next(iter(document.store.fact_resolution_claims.values()))
    assert claim.left_fact_id == proxy_tie.id
    assert claim.right_fact_id == named_tie.id
    assert claim.relation is ResolutionRelation.SAME_FACT
