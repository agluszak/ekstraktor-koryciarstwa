from __future__ import annotations

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
    def remap_mentions(document: ArticleDocument, remap: dict[str, str]) -> None:
        entity_by_id = {entity.entity_id: entity for entity in document.entities}
        deduplicated_mentions: dict[tuple[str | None, int, str], Mention] = {}
        for mention in document.mentions:
            if mention.entity_id:
                mention.entity_id = EntityID(remap.get(mention.entity_id, mention.entity_id))
            if mention.entity_id and mention.entity_id in entity_by_id:
                mention.normalized_text = entity_by_id[mention.entity_id].canonical_name
            key = (mention.entity_id, mention.sentence_index, mention.text)
            deduplicated_mentions[key] = mention
        document.mentions = list(deduplicated_mentions.values())

    @staticmethod
    def remap_fact_graph(document: ArticleDocument, remap: dict[str, str]) -> None:
        if not remap:
            return
        for fact in document.facts:
            fact.subject_entity_id = EntityID(
                remap.get(fact.subject_entity_id, fact.subject_entity_id)
            )
            if fact.object_entity_id:
                fact.object_entity_id = EntityID(
                    remap.get(fact.object_entity_id, fact.object_entity_id)
                )
            for field_name in (
                "position_entity_id",
                "owner_context_entity_id",
                "appointing_authority_entity_id",
                "governing_body_entity_id",
            ):
                value = getattr(fact, field_name)
                if isinstance(value, str):
                    setattr(fact, field_name, EntityID(remap.get(value, value)))
