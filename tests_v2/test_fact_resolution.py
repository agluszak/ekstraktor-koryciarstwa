from __future__ import annotations

from pipeline_v2.candidates import (
    ArgumentBindingCandidate,
    Assessment,
    EntityCandidate,
    EntityFiller,
    EntityResolutionClaim,
    TextFiller,
)
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import (
    ArgumentBindingCandidateId,
    DocumentId,
    EntityCandidateId,
    EventCandidateId,
    EvidenceId,
    MentionId,
    ProducerId,
    ResolutionClaimId,
    ScorerId,
    SentenceId,
)
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.nlp import EvidenceSpan, Mention, Sentence, Span
from pipeline_v2.scope import EvidenceScope
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
    MentionKind,
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


def _add_role_entity_with_descriptor_mention(
    document: ArticleDocument,
    *,
    entity_id: EntityCandidateId,
    mention_id: MentionId,
    evidence_id: EvidenceId,
    sentence_id: SentenceId,
    paragraph_index: int,
    text: str,
    start_char: int,
    end_char: int,
    head_lemma: str,
    kind: EntityKind = EntityKind.PERSON,
) -> None:
    document.store.add_evidence(
        EvidenceSpan(
            id=evidence_id,
            text=text,
            span=Span(start_char=start_char, end_char=end_char),
            sentence_id=sentence_id,
            paragraph_index=paragraph_index,
            source=ProducerId("test"),
        )
    )
    document.store.add_mention(
        Mention(
            id=mention_id,
            text=text,
            kind=MentionKind.DESCRIPTOR_NOUN_PHRASE,
            evidence_id=evidence_id,
            sentence_id=sentence_id,
            head_lemma=head_lemma,
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=entity_id,
            kind=kind,
            mention_ids=(mention_id,),
            canonical_hint=text,
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )


def _add_sentence_evidence(
    document: ArticleDocument,
    *,
    sentence_id: SentenceId,
    evidence_id: EvidenceId,
    sentence_index: int,
    paragraph_index: int,
    text: str,
    start_char: int,
) -> None:
    scope = EvidenceScope(paragraph_index=paragraph_index)
    document.store.add_sentence(
        Sentence(
            id=sentence_id,
            sentence_index=sentence_index,
            paragraph_index=paragraph_index,
            text=text,
            span=Span(start_char=start_char, end_char=start_char + len(text)),
            scope=scope,
        )
    )
    document.store.add_evidence(
        EvidenceSpan(
            id=evidence_id,
            text=text,
            span=Span(start_char=start_char, end_char=start_char + len(text)),
            sentence_id=sentence_id,
            paragraph_index=paragraph_index,
            source=ProducerId("test"),
            scope=scope,
        )
    )


def _bind_entity_with_evidence(
    document: ArticleDocument,
    *,
    binding_id: ArgumentBindingCandidateId,
    event_id: EventCandidateId,
    role: EventRole,
    entity_id: EntityCandidateId,
    evidence_id: EvidenceId,
) -> None:
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=binding_id,
            event_id=event_id,
            role=role,
            filler=EntityFiller(entity_id),
            evidence_ids=(evidence_id,),
            signals=(),
        )
    )


def _bind_text_with_evidence(
    document: ArticleDocument,
    *,
    binding_id: ArgumentBindingCandidateId,
    event_id: EventCandidateId,
    role: EventRole,
    value: str,
    evidence_id: EvidenceId,
    signals: tuple[RelationshipDetailSignal, ...] = (),
) -> None:
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=binding_id,
            event_id=event_id,
            role=role,
            filler=TextFiller(value),
            evidence_ids=(evidence_id,),
            signals=signals,
        )
    )


def test_probabilistic_inference_emits_same_fact_claim_and_suppresses_duplicate() -> None:
    document = _document()
    _add_sentence_evidence(
        document,
        sentence_id=SentenceId("sentence-1"),
        evidence_id=EvidenceId("evidence-1"),
        sentence_index=0,
        paragraph_index=0,
        text="Person został powołany do roli w Org.",
        start_char=0,
    )
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
        kind=FactKind.PUBLIC_ROLE_APPOINTMENT,
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
        kind=FactKind.PUBLIC_ROLE_APPOINTMENT,
        signals=(
            AppointmentLemmaSignal(lemma="powołać"),
            LocalPersonSignal(),
            LocalOrganizationSignal(),
            LocalRoleSignal(),
        ),
    )
    for event_id, prefix in ((first_event_id, "first"), (second_event_id, "second")):
        _bind_entity_with_evidence(
            document,
            binding_id=ArgumentBindingCandidateId(f"{prefix}-person"),
            event_id=event_id,
            role=EventRole.PERSON,
            entity_id=EntityCandidateId("person"),
            evidence_id=EvidenceId("evidence-1"),
        )
        _bind_entity_with_evidence(
            document,
            binding_id=ArgumentBindingCandidateId(f"{prefix}-org"),
            event_id=event_id,
            role=EventRole.ORGANIZATION,
            entity_id=EntityCandidateId("org"),
            evidence_id=EvidenceId("evidence-1"),
        )
        _bind_entity_with_evidence(
            document,
            binding_id=ArgumentBindingCandidateId(f"{prefix}-role"),
            event_id=event_id,
            role=EventRole.ROLE,
            entity_id=EntityCandidateId("role"),
            evidence_id=EvidenceId("evidence-1"),
        )

    ProbabilisticInferenceStage().run(document)

    claim = next(iter(document.store.fact_resolution_claims.values()))
    materialized_ids = {record.id for record in fact_records(document)}
    assert len(materialized_ids) == 1
    assert claim.left_fact_id in materialized_ids or claim.right_fact_id in materialized_ids
    assert claim.relation is ResolutionRelation.SAME_FACT
    assert claim.assessment.score >= 0.5
    surviving_id = next(iter(materialized_ids))
    assert surviving_id in document.materialized_fact_alternatives
    fact_alts = document.materialized_fact_alternatives[surviving_id]
    assert len(fact_alts) == 1
    suppressed_id = (
        claim.right_fact_id if surviving_id == claim.left_fact_id else claim.left_fact_id
    )
    assert fact_alts[0].record.id == suppressed_id


def test_probabilistic_inference_merges_governance_duplicates_with_matching_org() -> None:
    document = _document()
    _add_sentence_evidence(
        document,
        sentence_id=SentenceId("sentence-1"),
        evidence_id=EvidenceId("evidence-1"),
        sentence_index=0,
        paragraph_index=0,
        text="Person objął role w Org.",
        start_char=0,
    )
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
        kind=FactKind.PUBLIC_ROLE_APPOINTMENT,
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
        kind=FactKind.PUBLIC_ROLE_APPOINTMENT,
        signals=(
            AppointmentLemmaSignal(lemma="powołać"),
            LocalPersonSignal(),
            LocalOrganizationSignal(),
            LocalRoleSignal(),
        ),
    )
    _bind_entity_with_evidence(
        document,
        binding_id=ArgumentBindingCandidateId("first-person"),
        event_id=first_event_id,
        role=EventRole.PERSON,
        entity_id=EntityCandidateId("person"),
        evidence_id=EvidenceId("evidence-1"),
    )
    _bind_entity_with_evidence(
        document,
        binding_id=ArgumentBindingCandidateId("first-org"),
        event_id=first_event_id,
        role=EventRole.ORGANIZATION,
        entity_id=EntityCandidateId("org"),
        evidence_id=EvidenceId("evidence-1"),
    )
    _bind_entity_with_evidence(
        document,
        binding_id=ArgumentBindingCandidateId("first-role"),
        event_id=first_event_id,
        role=EventRole.ROLE,
        entity_id=EntityCandidateId("role-1"),
        evidence_id=EvidenceId("evidence-1"),
    )
    _bind_entity_with_evidence(
        document,
        binding_id=ArgumentBindingCandidateId("second-person"),
        event_id=second_event_id,
        role=EventRole.PERSON,
        entity_id=EntityCandidateId("person"),
        evidence_id=EvidenceId("evidence-1"),
    )
    _bind_entity_with_evidence(
        document,
        binding_id=ArgumentBindingCandidateId("second-org"),
        event_id=second_event_id,
        role=EventRole.ORGANIZATION,
        entity_id=EntityCandidateId("org"),
        evidence_id=EvidenceId("evidence-1"),
    )
    _bind_entity_with_evidence(
        document,
        binding_id=ArgumentBindingCandidateId("second-role"),
        event_id=second_event_id,
        role=EventRole.ROLE,
        entity_id=EntityCandidateId("role-2"),
        evidence_id=EvidenceId("evidence-1"),
    )

    ProbabilisticInferenceStage().run(document)

    claim = next(iter(document.store.fact_resolution_claims.values()))
    materialized_ids = {record.id for record in fact_records(document)}
    assert len(materialized_ids) == 1
    assert claim.left_fact_id in materialized_ids or claim.right_fact_id in materialized_ids
    assert claim.relation is ResolutionRelation.SAME_FACT
    surviving_id = next(iter(materialized_ids))
    assert surviving_id in document.materialized_fact_alternatives
    assert len(document.materialized_fact_alternatives[surviving_id]) == 1


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
        kind=FactKind.PUBLIC_ROLE_END,
        signals=(LocalPersonSignal(), LocalRoleSignal()),
    )
    add_event(
        document,
        event_id=second_event_id,
        kind=FactKind.PUBLIC_ROLE_END,
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

    ProbabilisticInferenceStage().run(document)

    assert document.store.fact_resolution_claims == {}


def test_probabilistic_inference_merges_proxy_and_named_ties_after_same_as_resolution() -> None:
    document = _document()
    _add_sentence_evidence(
        document,
        sentence_id=SentenceId("sentence-1"),
        evidence_id=EvidenceId("proxy-evidence"),
        sentence_index=0,
        paragraph_index=0,
        text="Opisano kuzyna target.",
        start_char=0,
    )
    _add_sentence_evidence(
        document,
        sentence_id=SentenceId("sentence-2"),
        evidence_id=EvidenceId("named-evidence"),
        sentence_index=1,
        paragraph_index=0,
        text="Rafal Dobosz to kuzyn target.",
        start_char=30,
    )
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
        kind=FactKind.PERSONAL_OR_POLITICAL_TIE,
        signals=(
            NamedKinshipLemmaSignal(lemma="kuzyn"),
            LocalSubjectSignal(),
            LocalObjectSignal(),
        ),
    )
    _bind_entity_with_evidence(
        document,
        binding_id=ArgumentBindingCandidateId("proxy-subject"),
        event_id=proxy_event_id,
        role=EventRole.SUBJECT,
        entity_id=EntityCandidateId("proxy-subject"),
        evidence_id=EvidenceId("proxy-evidence"),
    )
    _bind_entity_with_evidence(
        document,
        binding_id=ArgumentBindingCandidateId("proxy-object"),
        event_id=proxy_event_id,
        role=EventRole.OBJECT,
        entity_id=EntityCandidateId("target"),
        evidence_id=EvidenceId("proxy-evidence"),
    )
    _bind_text_with_evidence(
        document,
        binding_id=ArgumentBindingCandidateId("proxy-detail"),
        event_id=proxy_event_id,
        role=EventRole.RELATIONSHIP_DETAIL,
        value="family",
        evidence_id=EvidenceId("proxy-evidence"),
        signals=(RelationshipDetailSignal(detail=RelationshipDetail.FAMILY),),
    )
    _bind_entity_with_evidence(
        document,
        binding_id=ArgumentBindingCandidateId("named-subject"),
        event_id=named_event_id,
        role=EventRole.SUBJECT,
        entity_id=EntityCandidateId("named-subject"),
        evidence_id=EvidenceId("named-evidence"),
    )
    _bind_entity_with_evidence(
        document,
        binding_id=ArgumentBindingCandidateId("named-object"),
        event_id=named_event_id,
        role=EventRole.OBJECT,
        entity_id=EntityCandidateId("target"),
        evidence_id=EvidenceId("named-evidence"),
    )
    _bind_text_with_evidence(
        document,
        binding_id=ArgumentBindingCandidateId("named-detail"),
        event_id=named_event_id,
        role=EventRole.RELATIONSHIP_DETAIL,
        value="family",
        evidence_id=EvidenceId("named-evidence"),
        signals=(RelationshipDetailSignal(detail=RelationshipDetail.FAMILY),),
    )
    _bind_text_with_evidence(
        document,
        binding_id=ArgumentBindingCandidateId("named-context"),
        event_id=named_event_id,
        role=EventRole.CONTEXT,
        value="kuzyn Rafal Dobosz",
        evidence_id=EvidenceId("named-evidence"),
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

    ProbabilisticInferenceStage().run(document)

    claim = next(iter(document.store.fact_resolution_claims.values()))
    materialized_ids = {record.id for record in fact_records(document)}
    assert len(materialized_ids) == 1
    assert claim.left_fact_id in materialized_ids or claim.right_fact_id in materialized_ids
    assert claim.relation is ResolutionRelation.SAME_FACT
    surviving_id = next(iter(materialized_ids))
    assert surviving_id in document.materialized_fact_alternatives
    assert len(document.materialized_fact_alternatives[surviving_id]) == 1


def test_probabilistic_inference_merges_ties_when_subject_and_object_are_identical() -> None:
    # Two PERSONAL_OR_POLITICAL_TIE events with the same SUBJECT and OBJECT should be
    # detected as duplicate facts and deduplicated to a single materialized record.
    document = _document()
    add_entity(
        document,
        entity_id=EntityCandidateId("subject"),
        kind=EntityKind.PERSON,
        canonical_hint="Anna Kowalska",
    )
    add_entity(
        document,
        entity_id=EntityCandidateId("object"),
        kind=EntityKind.PERSON,
        canonical_hint="Jan Kowalski",
    )

    for event_id, prefix in (
        (EventCandidateId("event-role-1"), "first"),
        (EventCandidateId("event-role-2"), "second"),
    ):
        add_event(
            document,
            event_id=event_id,
            kind=FactKind.PERSONAL_OR_POLITICAL_TIE,
            signals=(
                NamedKinshipLemmaSignal(lemma="maz"),
                LocalSubjectSignal(),
                LocalObjectSignal(),
            ),
        )
        bind_entity(
            document,
            binding_id=ArgumentBindingCandidateId(f"{prefix}-subject"),
            event_id=event_id,
            role=EventRole.SUBJECT,
            entity_id=EntityCandidateId("subject"),
        )
        bind_entity(
            document,
            binding_id=ArgumentBindingCandidateId(f"{prefix}-object"),
            event_id=event_id,
            role=EventRole.OBJECT,
            entity_id=EntityCandidateId("object"),
        )
        bind_text(
            document,
            binding_id=ArgumentBindingCandidateId(f"{prefix}-detail"),
            event_id=event_id,
            role=EventRole.RELATIONSHIP_DETAIL,
            value=RelationshipDetail.FAMILY.value,
            signals=(RelationshipDetailSignal(detail=RelationshipDetail.FAMILY),),
        )

    ProbabilisticInferenceStage().run(document)

    assert len(document.materialized_fact_records) == 1


def test_probabilistic_inference_demotes_inverse_child_tie_duplicates() -> None:
    document = _document()
    add_entity(
        document,
        entity_id=EntityCandidateId("anna"),
        kind=EntityKind.PERSON,
        canonical_hint="Anna Kowalska",
    )
    add_entity(
        document,
        entity_id=EntityCandidateId("jan"),
        kind=EntityKind.PERSON,
        canonical_hint="Jan Kowalski",
    )
    for event_id, subject_id, object_id, prefix in (
        (
            EventCandidateId("child-1"),
            EntityCandidateId("anna"),
            EntityCandidateId("jan"),
            "first",
        ),
        (
            EventCandidateId("child-2"),
            EntityCandidateId("jan"),
            EntityCandidateId("anna"),
            "second",
        ),
    ):
        add_event(
            document,
            event_id=event_id,
            kind=FactKind.PERSONAL_OR_POLITICAL_TIE,
            signals=(
                NamedKinshipLemmaSignal(lemma="syn"),
                LocalSubjectSignal(),
                LocalObjectSignal(),
            ),
        )
        bind_entity(
            document,
            binding_id=ArgumentBindingCandidateId(f"{prefix}-subject"),
            event_id=event_id,
            role=EventRole.SUBJECT,
            entity_id=subject_id,
        )
        bind_entity(
            document,
            binding_id=ArgumentBindingCandidateId(f"{prefix}-object"),
            event_id=event_id,
            role=EventRole.OBJECT,
            entity_id=object_id,
        )
        bind_text(
            document,
            binding_id=ArgumentBindingCandidateId(f"{prefix}-detail"),
            event_id=event_id,
            role=EventRole.RELATIONSHIP_DETAIL,
            value=RelationshipDetail.CHILD.value,
            signals=(RelationshipDetailSignal(detail=RelationshipDetail.CHILD),),
        )

    ProbabilisticInferenceStage().run(document)

    tie_records = [
        record
        for record in fact_records(document)
        if record.kind is FactKind.PERSONAL_OR_POLITICAL_TIE
    ]
    assert len(tie_records) == 1
    tie_scores = [
        assessment.assessment.score
        for assessment in document.fact_assessments
        if assessment.materialized_fact_id in {record.id for record in tie_records}
    ]
    assert tie_scores
    assert max(tie_scores) < 0.5
