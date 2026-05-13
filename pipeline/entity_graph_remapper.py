from __future__ import annotations

from pipeline.document_graph import merge_entities
from pipeline.domain_types import EntityID
from pipeline.models import ArticleDocument, Entity
from pipeline.utils import unique_preserve_order


class EntityGraphRemapper:
    @staticmethod
    def merge_entity(target: Entity, source: Entity) -> None:
        target.aliases = unique_preserve_order(
            [*target.aliases, target.canonical_name, source.canonical_name, *source.aliases]
        )
        target.evidence.extend(
            evidence
            for evidence in source.evidence
            if not any(
                current.text == evidence.text
                and current.sentence_index == evidence.sentence_index
                and current.paragraph_index == evidence.paragraph_index
                and current.start_char == evidence.start_char
                and current.end_char == evidence.end_char
                for current in target.evidence
            )
        )
        merged_mention_ids = list(target.mention_ids)
        for mention_id in source.mention_ids:
            if mention_id not in merged_mention_ids:
                merged_mention_ids.append(mention_id)
        target.mention_ids = merged_mention_ids
        target.lemmas = unique_preserve_order([*target.lemmas, *source.lemmas])
        target.registry_id = target.registry_id or source.registry_id
        target.organization_kind = target.organization_kind or source.organization_kind
        target.is_proxy_person = target.is_proxy_person or source.is_proxy_person
        target.is_honorific_person_ref = (
            target.is_honorific_person_ref or source.is_honorific_person_ref
        )
        target.proxy_kind = target.proxy_kind or source.proxy_kind
        target.kinship_detail = target.kinship_detail or source.kinship_detail
        target.proxy_anchor_entity_id = (
            target.proxy_anchor_entity_id or source.proxy_anchor_entity_id
        )
        target.role_kind = target.role_kind or source.role_kind
        target.role_modifier = target.role_modifier or source.role_modifier

    @staticmethod
    def apply_remap(document: ArticleDocument, remap: dict[EntityID, EntityID]) -> None:
        merge_entities(document, remap, merge_fn=EntityGraphRemapper.merge_entity)
