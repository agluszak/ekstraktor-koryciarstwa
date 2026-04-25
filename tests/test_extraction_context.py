from pipeline.domain_types import ClauseID, ClusterID, DocumentID, EntityID, EntityType
from pipeline.extraction_context import ExtractionContext
from pipeline.models import ArticleDocument, ClauseUnit, ClusterMention, EntityCluster


def test_clusters_for_mentions_matches_span_before_text_fallback() -> None:
    person_mention = ClusterMention(
        text="Jan Kowalski",
        entity_type=EntityType.PERSON,
        sentence_index=0,
        paragraph_index=0,
        start_char=10,
        end_char=22,
        entity_id=EntityID("entity-person"),
    )
    organization_mention = ClusterMention(
        text="Urząd Gminy",
        entity_type=EntityType.PUBLIC_INSTITUTION,
        sentence_index=0,
        paragraph_index=0,
        start_char=40,
        end_char=51,
        entity_id=EntityID("entity-org"),
    )
    document = ArticleDocument(
        document_id=DocumentID("doc"),
        source_url=None,
        raw_html="",
        title="",
        publication_date=None,
        cleaned_text="",
        paragraphs=[],
        clusters=[
            EntityCluster(
                cluster_id=ClusterID("cluster-person"),
                entity_type=EntityType.PERSON,
                canonical_name="Jan Kowalski",
                normalized_name="jan kowalski",
                mentions=[person_mention],
            ),
            EntityCluster(
                cluster_id=ClusterID("cluster-org"),
                entity_type=EntityType.PUBLIC_INSTITUTION,
                canonical_name="Urząd Gminy",
                normalized_name="urząd gminy",
                mentions=[organization_mention],
            ),
        ],
    )
    clause_mention = ClusterMention(
        text="Jan Kowalski",
        entity_type=EntityType.PERSON,
        sentence_index=0,
        paragraph_index=0,
        start_char=11,
        end_char=23,
        entity_id=EntityID("entity-person"),
    )

    clusters = ExtractionContext.build(document).clusters_for_mentions(
        [clause_mention, organization_mention],
        {EntityType.PERSON},
    )

    assert [cluster.cluster_id for cluster in clusters] == [ClusterID("cluster-person")]


def test_paragraph_context_clusters_are_sorted_by_clause_distance() -> None:
    near = ClusterMention(
        text="Spółka",
        entity_type=EntityType.ORGANIZATION,
        sentence_index=2,
        paragraph_index=1,
        start_char=105,
        end_char=111,
    )
    far = ClusterMention(
        text="Fundusz",
        entity_type=EntityType.ORGANIZATION,
        sentence_index=0,
        paragraph_index=1,
        start_char=5,
        end_char=12,
    )
    document = ArticleDocument(
        document_id=DocumentID("doc"),
        source_url=None,
        raw_html="",
        title="",
        publication_date=None,
        cleaned_text="",
        paragraphs=[],
        clusters=[
            EntityCluster(
                cluster_id=ClusterID("far"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Fundusz",
                normalized_name="fundusz",
                mentions=[far],
            ),
            EntityCluster(
                cluster_id=ClusterID("near"),
                entity_type=EntityType.ORGANIZATION,
                canonical_name="Spółka",
                normalized_name="spółka",
                mentions=[near],
            ),
        ],
    )
    clause = ClauseUnit(
        clause_id=ClauseID("clause"),
        text="",
        trigger_head_text="",
        trigger_head_lemma="",
        sentence_index=2,
        paragraph_index=1,
        start_char=100,
        end_char=140,
    )

    clusters = ExtractionContext.build(document).paragraph_context_clusters(
        clause,
        {EntityType.ORGANIZATION},
    )

    assert [cluster.cluster_id for cluster in clusters] == [ClusterID("near"), ClusterID("far")]
