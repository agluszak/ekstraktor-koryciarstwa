from __future__ import annotations

from pipeline_v2.candidates import GovernanceFactCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.fact_resolution import FactResolutionStage
from pipeline_v2.ids import DocumentId, EntityCandidateId, FactCandidateId, ProducerId
from pipeline_v2.types import FactKind, ResolutionRelation


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
