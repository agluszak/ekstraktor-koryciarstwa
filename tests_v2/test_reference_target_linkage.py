from __future__ import annotations

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
    MentionId,
    ProducerId,
    SentenceId,
)
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.nlp import EvidenceSpan, Mention, Sentence, Span
from pipeline_v2.types import (
    CoreferenceProviderLinkSignal,
    EntityKind,
    EventRole,
    FactKind,
    GroundingKind,
    MentionKind,
    ThirdPersonPronounSignal,
)
from tests_v2.materialized import entity_argument


def test_reference_target_probability_propagation() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Jan Kowalski został odwołany. On odszedł.",
        paragraphs=("Jan Kowalski został odwołany. On odszedł.",),
    )

    sentence_id = SentenceId("sentence-1")
    document.store.add_sentence(
        Sentence(
            id=sentence_id,
            sentence_index=0,
            paragraph_index=0,
            text=document.cleaned_text,
            span=Span(0, len(document.cleaned_text)),
        )
    )

    # Evidences
    full_evidence_id = EvidenceId("evidence-full")
    on_evidence_id = EvidenceId("evidence-on")
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
            id=on_evidence_id,
            text="On",
            span=Span(29, 31),
            sentence_id=sentence_id,
            paragraph_index=0,
        )
    )

    # Mentions
    full_mention = MentionId("mention-full")
    on_mention = MentionId("mention-on")
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
            id=on_mention,
            text="On",
            kind=MentionKind.PRONOUN,
            evidence_id=on_evidence_id,
            sentence_id=sentence_id,
            head_lemma="on",
        )
    )

    # Entities
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("anchor"),
            kind=EntityKind.PERSON,
            mention_ids=(full_mention,),
            canonical_hint="Jan Kowalski",
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )

    # Proxy entity (depends on 'on-mention' reference)
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("proxy"),
            kind=EntityKind.PERSON,
            mention_ids=(),
            canonical_hint="On",
            grounding=GroundingKind.PROXY,
            source=ProducerId("test"),
            reference_ids=(on_mention,),
        )
    )

    # Reference resolution proposal: On -> Jan Kowalski
    document.reference_resolution_proposals.append(
        ReferenceResolutionProposal(
            reference_id=on_mention,
            candidate_entity_id=EntityCandidateId("anchor"),
            evidence_ids=(),
            retrieval_signals=(CoreferenceProviderLinkSignal(), ThirdPersonPronounSignal()),
        )
    )

    # Event 1: Governance Dismissal (with person='proxy')
    event_id = EventCandidateId("event-1")
    document.store.add_event_candidate(
        EventCandidate(
            id=event_id,
            kind=FactKind.GOVERNANCE_DISMISSAL,
            trigger_evidence_id=None,
            evidence_ids=(),
            source=ProducerId("test"),
        )
    )
    document.store.add_argument_binding(
        ArgumentBindingCandidate(
            id=ArgumentBindingCandidateId("binding-person"),
            event_id=event_id,
            role=EventRole.PERSON,
            filler=EntityFiller(EntityCandidateId("proxy")),
            evidence_ids=(),
        )
    )

    # Run the probabilistic stage
    ProbabilisticInferenceStage().run(document)

    # Check that the reference resolution claim was generated
    reference_claims = tuple(document.store.reference_resolution_claims.values())
    assert len(reference_claims) > 0

    # And check that the materialized fact contains the anchor (propagated via
    # reference/same-entity resolution). The scoring should link 'proxy' (which
    # has a governance dismissal event) to the resolved 'anchor'.
    # Since the fact is materialized, we should verify that we get a
    # governance dismissal for 'Jan Kowalski'.
    facts = document.materialized_fact_records
    assert len(facts) >= 1
    governance_facts = [f for f in facts if f.kind is FactKind.GOVERNANCE_DISMISSAL]
    assert len(governance_facts) >= 1

    assert any(
        entity_argument(governance_fact, "person") == EntityCandidateId("anchor")
        for governance_fact in governance_facts
    )
