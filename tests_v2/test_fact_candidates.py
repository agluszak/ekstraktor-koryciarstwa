from __future__ import annotations

from pipeline_v2.candidates import (
    AntiCorruptionInvestigationCandidate,
    AntiCorruptionReferralCandidate,
    GovernanceFactCandidate,
    MoneyTransferFactCandidate,
    PersonalTieFactCandidate,
    PublicEmploymentFactCandidate,
)
from pipeline_v2.ids import EntityCandidateId, EvidenceId, FactCandidateId, ProducerId
from pipeline_v2.store import ExtractionStore
from pipeline_v2.types import FactKind, RelationshipDetail


def test_governance_fact_candidate_indexes_participating_entities() -> None:
    store = ExtractionStore()
    candidate = GovernanceFactCandidate(
        id=FactCandidateId("appointment"),
        kind=FactKind.GOVERNANCE_APPOINTMENT,
        person_entity_id=EntityCandidateId("person"),
        organization_entity_id=EntityCandidateId("org"),
        role_entity_id=EntityCandidateId("role"),
        evidence_ids=(EvidenceId("evidence"),),
        source=ProducerId("test"),
    )

    store.add_fact_candidate(candidate)

    assert store.facts_involving_entity(EntityCandidateId("person")) == (candidate,)
    assert store.facts_involving_entity(EntityCandidateId("org")) == (candidate,)
    assert store.facts_involving_entity(EntityCandidateId("role")) == (candidate,)


def test_money_transfer_fact_candidate_preserves_amount_and_parties_in_record() -> None:
    candidate = MoneyTransferFactCandidate(
        id=FactCandidateId("funding"),
        kind=FactKind.FUNDING,
        source_entity_id=EntityCandidateId("funder"),
        target_entity_id=EntityCandidateId("recipient"),
        amount_text="100 tys. zł",
        evidence_ids=(EvidenceId("evidence"),),
        source=ProducerId("test"),
    )

    record = candidate.to_fact_record()

    assert record.kind is FactKind.FUNDING
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "funder", "entity_id": "funder"},
        {"role": "recipient", "entity_id": "recipient"},
        {"role": "amount", "value": "100 tys. zł"},
    )


def test_public_employment_fact_candidate_preserves_role_and_context_in_record() -> None:
    candidate = PublicEmploymentFactCandidate(
        id=FactCandidateId("employment"),
        person_entity_id=EntityCandidateId("person"),
        organization_entity_id=EntityCandidateId("org"),
        role_entity_id=EntityCandidateId("role"),
        evidence_ids=(EvidenceId("evidence"),),
        source=ProducerId("test"),
        context_text="umowa-zlecenie",
    )

    record = candidate.to_fact_record()

    assert record.kind is FactKind.PUBLIC_EMPLOYMENT
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "person", "entity_id": "person"},
        {"role": "organization", "entity_id": "org"},
        {"role": "role", "entity_id": "role"},
        {"role": "context", "value": "umowa-zlecenie"},
    )


def test_personal_tie_fact_candidate_preserves_relationship_detail_in_record() -> None:
    candidate = PersonalTieFactCandidate(
        id=FactCandidateId("tie"),
        subject_entity_id=EntityCandidateId("left"),
        object_entity_id=EntityCandidateId("right"),
        evidence_ids=(EvidenceId("evidence"),),
        source=ProducerId("test"),
        relationship_detail=RelationshipDetail.SPOUSE,
    )

    record = candidate.to_fact_record()

    assert record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "subject", "entity_id": "left"},
        {"role": "object", "entity_id": "right"},
        {"role": "context", "value": "spouse"},
    )


def test_anti_corruption_referral_candidate_preserves_semantic_roles_in_record() -> None:
    candidate = AntiCorruptionReferralCandidate(
        id=FactCandidateId("referral"),
        actor_entity_id=EntityCandidateId("complainant"),
        target_entity_id=EntityCandidateId("target"),
        institution_entity_id=EntityCandidateId("cba"),
        evidence_ids=(EvidenceId("evidence"),),
        source=ProducerId("test"),
        context_text="w sprawie zatrudnienia",
    )

    record = candidate.to_fact_record()

    assert record.kind is FactKind.ANTI_CORRUPTION_REFERRAL
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "complainant", "entity_id": "complainant"},
        {"role": "target", "entity_id": "target"},
        {"role": "institution", "entity_id": "cba"},
        {"role": "context", "value": "w sprawie zatrudnienia"},
    )


def test_anti_corruption_investigation_candidate_preserves_institution_and_target() -> None:
    candidate = AntiCorruptionInvestigationCandidate(
        id=FactCandidateId("investigation"),
        target_entity_id=EntityCandidateId("target"),
        institution_entity_id=EntityCandidateId("nik"),
        evidence_ids=(EvidenceId("evidence"),),
        source=ProducerId("test"),
        context_text="w sprawie Jana Nowaka",
    )

    record = candidate.to_fact_record()

    assert record.kind is FactKind.ANTI_CORRUPTION_INVESTIGATION
    assert tuple(argument.to_json() for argument in record.arguments) == (
        {"role": "target", "entity_id": "target"},
        {"role": "institution", "entity_id": "nik"},
        {"role": "context", "value": "w sprawie Jana Nowaka"},
    )
