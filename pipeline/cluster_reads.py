from __future__ import annotations

from pipeline.domain_types import (
    EntityID,
    EntityType,
    KinshipDetail,
    OrganizationKind,
    ProxyKind,
    RoleKind,
    RoleModifier,
)
from pipeline.models import Entity, EntityCluster


def entity_for_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> Entity | None:
    if cluster.primary_entity_id is not None:
        entity = entities_by_id.get(cluster.primary_entity_id)
        if entity is not None:
            return entity
    for entity_id in cluster.member_entity_ids:
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


def lemmas_for_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> list[str]:
    entity = entity_for_cluster(cluster, entities_by_id)
    return list(entity.lemmas) if entity is not None else []


def organization_kind_for_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> OrganizationKind | None:
    entity = entity_for_cluster(cluster, entities_by_id)
    return entity.organization_kind if entity is not None else None


def is_proxy_person_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> bool:
    entity = entity_for_cluster(cluster, entities_by_id)
    return entity.is_proxy_person if entity is not None else False


def proxy_kind_for_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> ProxyKind | None:
    entity = entity_for_cluster(cluster, entities_by_id)
    return entity.proxy_kind if entity is not None else None


def kinship_detail_for_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> KinshipDetail | None:
    entity = entity_for_cluster(cluster, entities_by_id)
    return entity.kinship_detail if entity is not None else None


def proxy_anchor_entity_id_for_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> EntityID | None:
    entity = entity_for_cluster(cluster, entities_by_id)
    return entity.proxy_anchor_entity_id if entity is not None else None


def role_kind_for_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> RoleKind | None:
    entity = entity_for_cluster(cluster, entities_by_id)
    return entity.role_kind if entity is not None else None


def role_modifier_for_cluster(
    cluster: EntityCluster,
    entities_by_id: dict[EntityID, Entity],
) -> RoleModifier | None:
    entity = entity_for_cluster(cluster, entities_by_id)
    return entity.role_modifier if entity is not None else None
