from __future__ import annotations

from pipeline_v2.candidates import EntityCandidate
from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import (
    ArgumentBindingCandidateId,
    DocumentId,
    EntityCandidateId,
    EventCandidateId,
    EvidenceId,
    MentionId,
    ProducerId,
)
from pipeline_v2.inference.factor_builders import FactInferenceGraphBuilder
from pipeline_v2.inference.resolution import ResolutionInferenceGraphBuilder
from pipeline_v2.nlp import EvidenceSpan, Mention, Span
from pipeline_v2.retrieval import SentenceEntityRetriever
from pipeline_v2.scope import ScopeCompatibilityPolicy
from pipeline_v2.segmentation import ParagraphSentenceSegmenter
from pipeline_v2.types import EntityKind, EventRole, FactKind, GroundingKind, MentionKind
from tests_v2.materialized import add_entity, add_event, bind_entity


def test_paragraph_sentence_segmenter_groups_consecutive_list_items_into_one_block() -> None:
    paragraphs = (
        "- Jan Kowalski został prezesem.",
        "- Anna Nowak została wiceprezeską.",
        "Komentarz końcowy.",
    )
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="\n\n".join(paragraphs),
        paragraphs=paragraphs,
    )

    ParagraphSentenceSegmenter().run(document)
    sentences = tuple(document.store.sentences.values())

    assert len(sentences) == 3
    first_scope = sentences[0].scope
    second_scope = sentences[1].scope
    third_scope = sentences[2].scope

    assert first_scope is not None
    assert second_scope is not None
    assert third_scope is not None
    assert first_scope.list_block_id is not None
    assert first_scope.list_block_id == second_scope.list_block_id
    assert first_scope.list_item_index == 0
    assert second_scope.list_item_index == 1
    assert third_scope.list_block_id is None
    assert third_scope.list_item_index is None


def test_scope_policy_blocks_same_event_across_different_list_items() -> None:
    paragraphs = (
        "- Jan Kowalski został prezesem.",
        "- Anna Nowak została wiceprezeską.",
    )
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text="\n\n".join(paragraphs),
        paragraphs=paragraphs,
    )

    ParagraphSentenceSegmenter().run(document)
    sentences = tuple(document.store.sentences.values())
    policy = ScopeCompatibilityPolicy()

    assert sentences[0].scope is not None
    assert sentences[1].scope is not None
    assert not policy.scope_allows_same_event(sentences[0].scope, sentences[1].scope)


def test_sentence_entity_retriever_blocks_cross_list_window_retrieval() -> None:
    paragraphs = (
        "- Jan Kowalski został prezesem.",
        "- Anna Nowak została wiceprezeską.",
    )
    cleaned_text = "\n\n".join(paragraphs)
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=paragraphs,
    )

    ParagraphSentenceSegmenter().run(document)
    first_sentence, second_sentence = tuple(document.store.sentences.values())
    mention_text = "Anna Nowak"
    start = cleaned_text.index(mention_text)
    evidence_id = EvidenceId("evidence-anna")
    document.store.add_evidence(
        EvidenceSpan(
            id=evidence_id,
            text=mention_text,
            span=Span(start_char=start, end_char=start + len(mention_text)),
            sentence_id=second_sentence.id,
            paragraph_index=second_sentence.paragraph_index,
            source=ProducerId("test"),
            scope=second_sentence.scope,
        )
    )
    mention_id = MentionId("mention-anna")
    document.store.add_mention(
        Mention(
            id=mention_id,
            text=mention_text,
            kind=MentionKind.NER,
            evidence_id=evidence_id,
            sentence_id=second_sentence.id,
        )
    )
    document.store.add_entity_candidate(
        EntityCandidate(
            id=EntityCandidateId("anna"),
            kind=EntityKind.PERSON,
            mention_ids=(mention_id,),
            canonical_hint=mention_text,
            grounding=GroundingKind.OBSERVED,
            source=ProducerId("test"),
        )
    )

    entities = SentenceEntityRetriever(document.store).entities_for_sentence_window(
        first_sentence,
        before=0,
        after=2,
    )

    assert entities == ()


def test_resolution_builder_blocks_same_event_proposals_across_list_items() -> None:
    paragraphs = (
        "- Jan Kowalski został prezesem portu.",
        "- Jan Kowalski został prezesem portu.",
    )
    cleaned_text = "\n\n".join(paragraphs)
    document = ArticleDocument(
        document_id=DocumentId("doc"),
        source_url=None,
        title="Title",
        publication_date=None,
        cleaned_text=cleaned_text,
        paragraphs=paragraphs,
    )

    ParagraphSentenceSegmenter().run(document)
    first_sentence, second_sentence = tuple(document.store.sentences.values())
    for evidence_id, sentence in (
        (EvidenceId("sentence-evidence-1"), first_sentence),
        (EvidenceId("sentence-evidence-2"), second_sentence),
    ):
        document.store.add_evidence(
            EvidenceSpan(
                id=evidence_id,
                text=sentence.text,
                span=sentence.span,
                sentence_id=sentence.id,
                paragraph_index=sentence.paragraph_index,
                source=ProducerId("test"),
                scope=sentence.scope,
            )
        )

    add_entity(
        document,
        entity_id=EntityCandidateId("person"),
        kind=EntityKind.PERSON,
        canonical_hint="Jan Kowalski",
    )
    add_entity(
        document,
        entity_id=EntityCandidateId("org"),
        kind=EntityKind.ORGANIZATION,
        canonical_hint="Port",
    )
    add_entity(
        document,
        entity_id=EntityCandidateId("role"),
        kind=EntityKind.ROLE,
        canonical_hint="prezes",
    )
    add_event(document, event_id=EventCandidateId("event-1"), kind=FactKind.PUBLIC_ROLE_HOLDING)
    add_event(document, event_id=EventCandidateId("event-2"), kind=FactKind.PUBLIC_ROLE_HOLDING)
    for event_id, evidence_id in (
        (EventCandidateId("event-1"), EvidenceId("sentence-evidence-1")),
        (EventCandidateId("event-2"), EvidenceId("sentence-evidence-2")),
    ):
        bind_entity(
            document,
            binding_id=ArgumentBindingCandidateId(f"{event_id}-person"),
            event_id=event_id,
            role=EventRole.PERSON,
            entity_id=EntityCandidateId("person"),
            evidence_ids=(evidence_id,),
        )
        bind_entity(
            document,
            binding_id=ArgumentBindingCandidateId(f"{event_id}-org"),
            event_id=event_id,
            role=EventRole.ORGANIZATION,
            entity_id=EntityCandidateId("org"),
            evidence_ids=(evidence_id,),
        )
        bind_entity(
            document,
            binding_id=ArgumentBindingCandidateId(f"{event_id}-role"),
            event_id=event_id,
            role=EventRole.ROLE,
            entity_id=EntityCandidateId("role"),
            evidence_ids=(evidence_id,),
        )

    fact_graph = FactInferenceGraphBuilder().build(document)
    resolution_graph = ResolutionInferenceGraphBuilder().build(
        document=document,
        fact_graph=fact_graph,
    )

    assert resolution_graph.same_event_proposal_by_variable_id == {}
