from __future__ import annotations

from pipeline.document_graph import sync_entity_mentions
from pipeline.domain_types import EntityID
from pipeline.models import ArticleDocument, Entity, Mention
from pipeline.utils import unique_preserve_order


class EntityGraphRemapper:
    @staticmethod
    def merge_entity(target: Entity, source: Entity) -> None:
        target.aliases = unique_preserve_order(
            [*target.aliases, target.canonical_name, source.canonical_name, *source.aliases]
        )
        target.evidence.extend(source.evidence)
        if len(source.aliases) > len(target.aliases):
            target.lemmas = source.lemmas if source.lemmas else target.lemmas

    @staticmethod
    def remap_mentions(document: ArticleDocument, remap: dict[EntityID, EntityID]) -> None:
        entity_by_id = {entity.entity_id: entity for entity in document.entities}
        deduplicated_mentions: dict[
            tuple[EntityID | None, int, int, int, int, str, str, str],
            Mention,
        ] = {}
        for mention in document.mentions:
            if mention.entity_id:
                mention.entity_id = remap.get(mention.entity_id, mention.entity_id)
            if mention.entity_id and mention.entity_id in entity_by_id:
                target_entity = entity_by_id[mention.entity_id]
                mention.normalized_text = target_entity.canonical_name
                mention.entity_type = target_entity.entity_type
            key = (
                mention.entity_id,
                mention.sentence_index,
                mention.paragraph_index,
                mention.start_char,
                mention.end_char,
                mention.text,
                mention.mention_kind.value,
                mention.entity_type.value,
            )
            deduplicated_mentions[key] = mention
        document.mentions = list(deduplicated_mentions.values())
        for cluster in document.clusters:
            if cluster.primary_entity_id is not None:
                cluster.primary_entity_id = remap.get(
                    cluster.primary_entity_id,
                    cluster.primary_entity_id,
                )
            remapped_member_entity_ids: list[EntityID] = []
            for entity_id in cluster.member_entity_ids:
                remapped_entity_id = remap.get(entity_id, entity_id)
                if remapped_entity_id not in remapped_member_entity_ids:
                    remapped_member_entity_ids.append(remapped_entity_id)
            cluster.member_entity_ids = remapped_member_entity_ids
            for mention in cluster.mentions:
                if mention.entity_id:
                    mention.entity_id = remap.get(mention.entity_id, mention.entity_id)
                if mention.entity_id and mention.entity_id in entity_by_id:
                    mention.entity_type = entity_by_id[mention.entity_id].entity_type
        sync_entity_mentions(document)

    @staticmethod
    def remap_fact_graph(document: ArticleDocument, remap: dict[EntityID, EntityID]) -> None:
        if not remap:
            return
        for fact in document.facts:
            fact.subject_entity_id = remap.get(fact.subject_entity_id, fact.subject_entity_id)
            if fact.object_entity_id:
                fact.object_entity_id = remap.get(fact.object_entity_id, fact.object_entity_id)
            for field_name in (
                "position_entity_id",
                "owner_context_entity_id",
                "appointing_authority_entity_id",
                "governing_body_entity_id",
            ):
                value = getattr(fact, field_name)
                if isinstance(value, str):
                    entity_id = EntityID(value)
                    setattr(fact, field_name, remap.get(entity_id, entity_id))
