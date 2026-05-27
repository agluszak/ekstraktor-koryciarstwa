from __future__ import annotations

from pipeline_v2.candidates import ReferenceResolutionProposal
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import (
    DocumentId,
    EntityCandidateId,
    EvidenceId,
    MentionId,
    SentenceId,
)
from pipeline_v2.inference.stage import ProbabilisticInferenceStage
from pipeline_v2.nlp import EvidenceSpan, Mention, ReferenceMention, Sentence, Span
from pipeline_v2.producers import SimpleEntityCandidateProducer
from pipeline_v2.scope import EvidenceScope
from pipeline_v2.types import (
    CoreferenceProviderLinkSignal,
    MentionKind,
    ReferenceKind,
    ResolutionRelation,
)


def test_resolution_scoring_stage_emits_scored_entity_resolution_claims() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Jan Kowalski. Kowalski.",
        paragraphs=("Jan Kowalski. Kowalski.",),
    )
    sentence_id = document.store.add_sentence(
        Sentence(
            id=SentenceId("sentence-1"),
            sentence_index=0,
            paragraph_index=0,
            scope=EvidenceScope(paragraph_index=0),
            text="Jan Kowalski. Kowalski.",
            span=Span(0, len(document.cleaned_text)),
        )
    )
    full_evidence_id = document.store.add_evidence(
        EvidenceSpan(
            id=EvidenceId("evidence-full"),
            text="Jan Kowalski",
            span=Span(0, 12),
            sentence_id=sentence_id,
            paragraph_index=0,
        )
    )
    partial_evidence_id = document.store.add_evidence(
        EvidenceSpan(
            id=EvidenceId("evidence-partial"),
            text="Kowalski",
            span=Span(14, 22),
            sentence_id=sentence_id,
            paragraph_index=0,
        )
    )
    full_mention = MentionId("mention-full")
    partial_mention = MentionId("mention-partial")
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
            id=partial_mention,
            text="Kowalski",
            kind=MentionKind.SURNAME_ONLY,
            evidence_id=partial_evidence_id,
            sentence_id=sentence_id,
            head_lemma="kowalski",
        )
    )
    producer = SimpleEntityCandidateProducer()
    full_id = producer.add_full_person(
        document.store,
        candidate_id=EntityCandidateId("person-full"),
        mention_ids=(full_mention,),
        given_name_lemma="jan",
        surname_base="kowalski",
        canonical_hint="Jan Kowalski",
    )
    partial_id = producer.add_surname_only_person(
        document.store,
        candidate_id=EntityCandidateId("person-partial"),
        mention_ids=(partial_mention,),
        canonical_hint="Kowalski",
    )

    ProbabilisticInferenceStage().run(document)

    claims = tuple(document.store.resolution_claims.values())
    assert len(claims) == 1
    assert {claims[0].left_entity_id, claims[0].right_entity_id} == {partial_id, full_id}
    assert claims[0].relation is ResolutionRelation.SAME_AS
    assert claims[0].assessment.score >= 0.5


def test_resolution_scoring_stage_emits_scored_reference_resolution_claims() -> None:
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="Jan Kowalski. Jego żona.",
        paragraphs=("Jan Kowalski. Jego żona.",),
    )
    sentence_id = document.store.add_sentence(
        Sentence(
            id=SentenceId("sentence-1"),
            sentence_index=0,
            paragraph_index=0,
            scope=EvidenceScope(paragraph_index=0),
            text="Jan Kowalski. Jego żona.",
            span=Span(0, len(document.cleaned_text)),
        )
    )
    reference_evidence_id = document.store.add_evidence(
        EvidenceSpan(
            id=EvidenceId("evidence-reference"),
            text="Jego",
            span=Span(14, 18),
            sentence_id=sentence_id,
            paragraph_index=0,
        )
    )
    reference_id = document.store.add_reference(
        ReferenceMention(
            id=MentionId("reference-1"),
            text="Jego",
            kind=ReferenceKind.POSSESSIVE_PRONOUN,
            evidence_id=reference_evidence_id,
            sentence_id=sentence_id,
        )
    )
    candidate_id = EntityCandidateId("person")
    document.reference_resolution_proposals.append(
        ReferenceResolutionProposal(
            reference_id=reference_id,
            candidate_entity_id=candidate_id,
            evidence_ids=(reference_evidence_id,),
            retrieval_signals=(CoreferenceProviderLinkSignal(),),
        )
    )

    ProbabilisticInferenceStage().run(document)

    claims = tuple(document.store.reference_resolution_claims.values())
    assert len(claims) == 1
    assert claims[0].reference_id == reference_id
    assert claims[0].candidate_entity_id == candidate_id
    assert claims[0].relation is ResolutionRelation.REFERENT_OF
    assert claims[0].assessment.score >= 0.7
