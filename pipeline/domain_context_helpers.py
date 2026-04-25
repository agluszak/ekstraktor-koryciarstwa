from __future__ import annotations

from collections.abc import Iterable

from pipeline.domain_types import EntityType
from pipeline.extraction_context import ExtractionContext
from pipeline.models import ArticleDocument, ClauseUnit, ClusterMention, EntityCluster

ATTRIBUTION_SPEECH_LEMMAS = frozenset(
    {
        "mówić",
        "powiedzieć",
        "tłumaczyć",
        "przekonywać",
        "dodać",
        "komentować",
        "zaznaczyć",
        "podkreślić",
        "wyjaśnić",
        "ocenić",
        "przypomnieć",
        "stwierdzić",
        "odnieść",
    }
)


def clusters_for_mentions(
    document: ArticleDocument,
    mentions: Iterable[ClusterMention],
    entity_types: set[EntityType],
) -> list[EntityCluster]:
    return ExtractionContext.build(document).clusters_for_mentions(mentions, entity_types)


def cluster_for_mention(
    document: ArticleDocument,
    mention_ref: ClusterMention,
) -> EntityCluster | None:
    return ExtractionContext.build(document).cluster_for_mention(mention_ref)


def paragraph_context_clusters(
    document: ArticleDocument,
    clause: ClauseUnit,
    entity_types: set[EntityType],
) -> list[EntityCluster]:
    return ExtractionContext.build(document).paragraph_context_clusters(clause, entity_types)


def merge_clusters(
    primary: list[EntityCluster],
    secondary: list[EntityCluster],
) -> list[EntityCluster]:
    return ExtractionContext.merge_clusters(primary, secondary)


def cluster_clause_distance(cluster: EntityCluster, clause: ClauseUnit) -> tuple[int, int]:
    return ExtractionContext.cluster_clause_distance(cluster, clause)


def sort_clusters_by_clause_distance(
    clusters: list[EntityCluster],
    clause: ClauseUnit,
) -> list[EntityCluster]:
    return sorted(clusters, key=lambda cluster: cluster_clause_distance(cluster, clause))


def best_cluster_near_offset(
    clusters: list[EntityCluster],
    offset: int,
) -> EntityCluster | None:
    return ExtractionContext.best_cluster_near_offset(clusters, offset)
