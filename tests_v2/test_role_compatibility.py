from __future__ import annotations

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    Assessment,
    EntityCandidate,
    EntityFactArgument,
    EntityFiller,
    EntityResolutionClaim,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import (
    ArgumentBindingCandidateId,
    DocumentId,
    EntityCandidateId,
    EventCandidateId,
    ProducerId,
    ResolutionClaimId,
    ScorerId,
)
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.types import (
    EntityKind,
    EventRole,
    FactArgumentRole,
    FactKind,
    GroundingKind,
    PublicEmploymentLemmaSignal,
    ResolutionRelation,
    WeakSyntacticBindingSignal,
)


def test_inference_prefers_real_organization_over_party_for_governance_target() -> None:
    document = _document()
    person_id = _entity(document, "person", EntityKind.PERSON, "Jan Kowalski")
    organization_id = _entity(
        document,
        "organization",
        EntityKind.ORGANIZATION,
        "Totalizator Sportowy",
    )
    party_id = _entity(document, "party", EntityKind.POLITICAL_PARTY, "PSL")
    event_id = EventCandidateId("governance-event")
    document.store.add_event_candidate(_event(event_id, FactKind.PUBLIC_ROLE_APPOINTMENT))
    _binding(document, event_id, EventRole.PERSON, person_id)
    _binding(document, event_id, EventRole.ORGANIZATION, organization_id)
    _binding(document, event_id, EventRole.ORGANIZATION, party_id)

    ProbabilisticInferenceStage().run(document)

    governance_facts = [
        record
        for record in document.materialized_fact_records
        if record.kind is FactKind.PUBLIC_ROLE_APPOINTMENT
    ]
    assert governance_facts
    organization_arguments = set()
    for record in governance_facts:
        for argument in record.arguments:
            match argument:
                case EntityFactArgument(role=FactArgumentRole.ORGANIZATION, entity_id=entity_id):
                    organization_arguments.add(entity_id)
    assert organization_id in organization_arguments
    assert party_id not in organization_arguments


def test_weak_required_role_binding_lowers_materialized_public_employment_score() -> None:
    strong_document = _employment_document(employee_signals=())
    weak_document = _employment_document(
        employee_signals=(WeakSyntacticBindingSignal(reason="test weak binding"),)
    )

    ProbabilisticInferenceStage().run(strong_document)
    ProbabilisticInferenceStage().run(weak_document)

    assert _top_fact_score(strong_document, FactKind.PUBLIC_EMPLOYMENT) > _top_fact_score(
        weak_document,
        FactKind.PUBLIC_EMPLOYMENT,
    )


def test_inference_prefers_distinct_object_when_other_object_resolves_to_subject() -> None:
    document = _document()
    subject_id = _entity(document, "subject", EntityKind.PERSON, "Jan Kowalski")
    alias_id = _entity(document, "alias", EntityKind.PERSON, "J. Kowalski")
    other_id = _entity(document, "other", EntityKind.PERSON, "Piotr Nowak")
    event_id = EventCandidateId("tie-event")
    document.store.add_event_candidate(_event(event_id, FactKind.PERSONAL_OR_POLITICAL_TIE))
    _binding(document, event_id, EventRole.SUBJECT, subject_id)
    _binding(document, event_id, EventRole.OBJECT, alias_id)
    _binding(document, event_id, EventRole.OBJECT, other_id)
    document.store.add_resolution_claim(
        EntityResolutionClaim(
            id=ResolutionClaimId("resolution-0"),
            left_entity_id=subject_id,
            right_entity_id=alias_id,
            relation=ResolutionRelation.SAME_AS,
            evidence_ids=(),
            assessment=Assessment(
                score=0.95,
                positive_signals=(),
                negative_signals=(),
                scorer_id=ScorerId("test"),
            ),
            source=ProducerId("test"),
        )
    )

    ProbabilisticInferenceStage().run(document)

    tie_facts = [
        record
        for record in document.materialized_fact_records
        if record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
    ]
    assert tie_facts
    object_arguments: set[EntityCandidateId] = set()
    for record in tie_facts:
        for argument in record.arguments:
            match argument:
                case EntityFactArgument(role=FactArgumentRole.OBJECT, entity_id=entity_id):
                    object_arguments.add(entity_id)
                case _:
                    continue
    assert other_id in object_arguments
    assert alias_id not in object_arguments


def _employment_document(*, employee_signals) -> ArticleDocument:
    document = _document()
    employee_id = _entity(document, "employee", EntityKind.PERSON, "Jan Kowalski")
    workplace_id = _entity(document, "workplace", EntityKind.ORGANIZATION, "Urząd")
    event_id = EventCandidateId("employment-event")
    document.store.add_event_candidate(
        _event(
            event_id,
            FactKind.PUBLIC_EMPLOYMENT,
            signals=(PublicEmploymentLemmaSignal(lemma="zatrudnić"),),
        )
    )
    _binding(document, event_id, EventRole.EMPLOYEE, employee_id, signals=employee_signals)
    _binding(document, event_id, EventRole.WORKPLACE, workplace_id)
    return document


def _top_fact_score(document: ArticleDocument, kind: FactKind) -> float:
    scores = [
        assessment.assessment.score
        for assessment in document.fact_assessments
        if any(
            record.id == assessment.materialized_fact_id and record.kind is kind
            for record in document.materialized_fact_records
        )
    ]
    return max(scores, default=0.0)


def _document() -> ArticleDocument:
    return ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Text.",
        paragraphs=("Text.",),
    )


def _entity(
    document: ArticleDocument,
    suffix: str,
    kind: EntityKind,
    canonical_hint: str,
) -> EntityCandidateId:
    entity_id = EntityCandidateId(f"entity-{suffix}")
    document.store.add_entity_candidate(
        EntityCandidate(
            id=entity_id,
            kind=kind,
            mention_ids=(),
            canonical_hint=canonical_hint,
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )
    return entity_id


def _event(event_id: EventCandidateId, kind: FactKind, *, signals=()):
    from pipeline_v2.candidates import EventCandidate

    return EventCandidate(
        id=event_id,
        kind=kind,
        trigger_evidence_id=None,
        evidence_ids=(),
        source=ProducerId("test"),
        signals=signals,
    )


def _binding(
    document: ArticleDocument,
    event_id: EventCandidateId,
    role: EventRole,
    entity_id: EntityCandidateId,
    *,
    signals=(),
) -> None:
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId(f"binding-{event_id}-{role.value}-{entity_id}"),
            event_id=event_id,
            role=role,
            filler=EntityFiller(entity_id),
            evidence_ids=(),
            signals=signals,
        )
    )
