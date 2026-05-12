from __future__ import annotations

from pipeline.domain_types import EntityID, EntityType
from pipeline.models import Entity, EntityCluster


def entity_for_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> Entity | None:
    if cluster.primary_entity_id is not None:
        entity = entities_by_id.get(cluster.primary_entity_id)
        if entity is not None:
            return entity
    seen_entity_ids: set[EntityID] = set()
    for entity_id in (mention.entity_id for mention in cluster.mentions if mention.entity_id):
        if entity_id in seen_entity_ids:
            continue
        seen_entity_ids.add(entity_id)
        entity = entities_by_id.get(entity_id)
        if entity is not None:
            return entity
    return next(
        (
            entities_by_id[mention.entity_id]
            for mention in cluster.mentions
            if mention.entity_id in entities_by_id
        ),
        None,
    )


def entity_type_for_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> EntityType:
    entity = entity_for_cluster(cluster, entities_by_id)
    if entity is not None:
        return entity.entity_type
    return cluster.mentions[0].entity_type if cluster.mentions else EntityType.ORGANIZATION


def canonical_name_for_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> str:
    entity = entity_for_cluster(cluster, entities_by_id)
    if entity is not None:
        return entity.canonical_name
    return cluster.mentions[0].text if cluster.mentions else str(cluster.cluster_id)


def normalized_name_for_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> str:
    entity = entity_for_cluster(cluster, entities_by_id)
    if entity is not None:
        return entity.normalized_name
    return cluster.mentions[0].text if cluster.mentions else str(cluster.cluster_id)


def aliases_for_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> list[str]:
    entity = entity_for_cluster(cluster, entities_by_id)
    aliases = list(entity.aliases) if entity is not None else []
    for mention in cluster.mentions:
        if mention.text not in aliases:
            aliases.append(mention.text)
    return aliases
