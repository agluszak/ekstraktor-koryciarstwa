"""Post-linking deduplication of document entity lists."""

from __future__ import annotations

from pipeline.domain_types import EntityID, EntityType
from pipeline.models import Entity


class RegistryDeduplicator:
    """Merges entities that resolved to the same registry / KB id."""

    @staticmethod
    def deduplicate_by_registry(
        entities: list[Entity],
    ) -> tuple[list[Entity], dict[EntityID, EntityID]]:
        """Merge entities that resolved to the same registry_id.

        Returns the deduplicated list and a mapping from removed entity_ids
        to the primary entity_id they were merged into.
        """
        registry_map: dict[str, Entity] = {}
        id_remap: dict[EntityID, EntityID] = {}
        result: list[Entity] = []
        for entity in entities:
            if entity.is_proxy_person or entity.is_honorific_person_ref:
                result.append(entity)
                continue
            rid = entity.registry_id
            if rid is None or rid not in registry_map:
                if rid is not None:
                    registry_map[rid] = entity
                result.append(entity)
            else:
                primary = registry_map[rid]
                primary.aliases = list(
                    dict.fromkeys(
                        [*primary.aliases, *entity.aliases, entity.canonical_name],
                    )
                )
                primary.evidence.extend(entity.evidence)
                id_remap[entity.entity_id] = primary.entity_id
        return result, id_remap

    @staticmethod
    def deduplicate_exact_names(
        entities: list[Entity],
    ) -> tuple[list[Entity], dict[EntityID, EntityID]]:
        """Merge entities that share an exact (case-folded) canonical name and compatible type."""
        exact_name_map: dict[tuple[str, str], Entity] = {}
        id_remap: dict[EntityID, EntityID] = {}
        result: list[Entity] = []
        for entity in entities:
            if entity.is_proxy_person or entity.is_honorific_person_ref:
                result.append(entity)
                continue
            key_type = entity.entity_type.value
            if entity.entity_type in {
                EntityType.ORGANIZATION,
                EntityType.PUBLIC_INSTITUTION,
            }:
                key_type = "org-or-public-institution"
            key = (key_type, entity.canonical_name.casefold())
            existing = exact_name_map.get(key)
            if existing is None:
                exact_name_map[key] = entity
                result.append(entity)
                continue
            existing.aliases = list(
                dict.fromkeys(
                    [*existing.aliases, existing.canonical_name, *entity.aliases],
                )
            )
            existing.evidence.extend(entity.evidence)
            id_remap[entity.entity_id] = existing.entity_id
        return result, id_remap
