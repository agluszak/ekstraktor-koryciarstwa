from pipeline.domain_types import ClusterID, DocumentID, EntityID, EntityType
from pipeline.entity_graph_remapper import EntityGraphRemapper
from pipeline.models import ArticleDocument, ClusterMention, Entity, EntityCluster, Mention


def test_remap_mentions_deduplicates_member_entity_ids_after_many_to_one_remap() -> None:
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
        clusters=[
            EntityCluster(
                cluster_id=ClusterID("cluster-person"),
                mentions=[
                    ClusterMention(
                        text="Jan Kowalski",
                        entity_type=EntityType.PERSON,
                        sentence_index=0,
                        paragraph_index=0,
                        start_char=0,
                        end_char=12,
                        entity_id=source_id,
                    ),
                    ClusterMention(
                        text="Kowalski",
                        entity_type=EntityType.PERSON,
                        sentence_index=0,
                        paragraph_index=0,
                        start_char=4,
                        end_char=12,
                        entity_id=target_id,
                    ),
                ],
                primary_entity_id=source_id,
                member_entity_ids=[source_id, target_id],
            )
        ],
    )

    EntityGraphRemapper.remap_mentions(document, {source_id: target_id})

    assert document.clusters[0].primary_entity_id == target_id
    assert document.clusters[0].member_entity_ids == [target_id]
    assert [mention.entity_id for mention in document.clusters[0].mentions] == [
        target_id,
        target_id,
    ]
