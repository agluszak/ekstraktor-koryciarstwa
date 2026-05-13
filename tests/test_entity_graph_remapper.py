from pipeline.document_graph import derived_clusters
from pipeline.domain_types import (
    DocumentID,
    EntityID,
    EntityType,
    MentionKind,
)
from pipeline.entity_graph_remapper import EntityGraphRemapper
from pipeline.models import ArticleDocument, Entity, Mention


def test_apply_remap_deduplicates_mentions_after_many_to_one_merge() -> None:
    target_id = EntityID("entity-target")
    source_id = EntityID("entity-source")
    document = ArticleDocument(
        document_id=DocumentID("doc-remap"),
        source_url=None,
        raw_html="",
        title="",
        publication_date=None,
        cleaned_text="Jan Kowalski",
        paragraphs=["Jan Kowalski"],
        entities=[
            Entity(
                entity_id=target_id,
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="jan kowalski",
            ),
            Entity(
                entity_id=source_id,
                entity_type=EntityType.PERSON,
                canonical_name="J. Kowalski",
                normalized_name="j kowalski",
            ),
        ],
        mentions=[
            Mention(
                text="Jan Kowalski",
                normalized_text="Jan Kowalski",
                entity_type=EntityType.PERSON,
                sentence_index=0,
                paragraph_index=0,
                start_char=0,
                end_char=12,
                entity_id=source_id,
            )
        ],
    )
    document.mentions.append(
        Mention(
            text="Kowalski",
            normalized_text="Jan Kowalski",
            entity_type=EntityType.PERSON,
            sentence_index=0,
            paragraph_index=0,
            start_char=4,
            end_char=12,
            entity_id=target_id,
        )
    )
    EntityGraphRemapper.apply_remap(document, {source_id: target_id})
    EntityGraphRemapper.apply_remap(document, {source_id: target_id})
    merged_cluster = derived_clusters(document)[0]
    assert merged_cluster.primary_entity_id == target_id
    assert [mention.entity_id for mention in merged_cluster.mentions] == [
        target_id,
        target_id,
    ]


def test_remap_mentions_keeps_distinct_same_text_spans_in_same_sentence() -> None:
    target_id = EntityID("entity-target")
    source_id = EntityID("entity-source")
    document = ArticleDocument(
        document_id=DocumentID("doc-remap-spans"),
        source_url=None,
        raw_html="",
        title="",
        publication_date=None,
        cleaned_text="ABC ABC",
        paragraphs=["ABC ABC"],
        entities=[
            Entity(
                entity_id=target_id,
                entity_type=EntityType.ORGANIZATION,
                canonical_name="ABC",
                normalized_name="ABC",
            ),
            Entity(
                entity_id=source_id,
                entity_type=EntityType.ORGANIZATION,
                canonical_name="ABC SA",
                normalized_name="ABC SA",
            ),
        ],
        mentions=[
            Mention(
                text="ABC",
                normalized_text="ABC",
                entity_type=EntityType.ORGANIZATION,
                sentence_index=0,
                paragraph_index=0,
                start_char=0,
                end_char=3,
                mention_kind=MentionKind.NAMED_ENTITY,
                entity_id=source_id,
            ),
            Mention(
                text="ABC",
                normalized_text="ABC",
                entity_type=EntityType.ORGANIZATION,
                sentence_index=0,
                paragraph_index=0,
                start_char=4,
                end_char=7,
                mention_kind=MentionKind.NAMED_ENTITY,
                entity_id=source_id,
            ),
        ],
    )

    EntityGraphRemapper.apply_remap(document, {source_id: target_id})

    assert [(mention.start_char, mention.end_char) for mention in document.mentions] == [
        (0, 3),
        (4, 7),
    ]
    assert all(mention.entity_id == target_id for mention in document.mentions)


def test_remap_mentions_updates_entity_type_before_deduplication() -> None:
    target_id = EntityID("entity-target")
    source_id = EntityID("entity-source")
    document = ArticleDocument(
        document_id=DocumentID("doc-remap-type"),
        source_url=None,
        raw_html="",
        title="",
        publication_date=None,
        cleaned_text="ABC",
        paragraphs=["ABC"],
        entities=[
            Entity(
                entity_id=target_id,
                entity_type=EntityType.ORGANIZATION,
                canonical_name="ABC",
                normalized_name="ABC",
            ),
            Entity(
                entity_id=source_id,
                entity_type=EntityType.PERSON,
                canonical_name="ABC",
                normalized_name="ABC",
            ),
        ],
        mentions=[
            Mention(
                text="ABC",
                normalized_text="ABC",
                entity_type=EntityType.PERSON,
                sentence_index=0,
                paragraph_index=0,
                start_char=0,
                end_char=3,
                mention_kind=MentionKind.NAMED_ENTITY,
                entity_id=source_id,
            ),
            Mention(
                text="ABC",
                normalized_text="ABC",
                entity_type=EntityType.ORGANIZATION,
                sentence_index=0,
                paragraph_index=0,
                start_char=0,
                end_char=3,
                mention_kind=MentionKind.NAMED_ENTITY,
                entity_id=target_id,
            ),
        ],
    )

    EntityGraphRemapper.apply_remap(document, {source_id: target_id})

    assert len(document.mentions) == 1
    assert document.mentions[0].entity_type == EntityType.ORGANIZATION
    assert document.mentions[0].entity_id == target_id
