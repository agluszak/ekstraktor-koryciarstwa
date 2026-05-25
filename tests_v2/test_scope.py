from __future__ import annotations

from pipeline_v2.document import ArticleDocument
from pipeline_v2.ids import DocumentId
from pipeline_v2.scope import ScopeCompatibilityPolicy
from pipeline_v2.segmentation import ParagraphSentenceSegmenter


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
