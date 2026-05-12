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
        target.evidence.extend(source.evidence)
        if len(source.aliases) > len(target.aliases):
            target.lemmas = source.lemmas if source.lemmas else target.lemmas

    @staticmethod
    def apply_remap(document: ArticleDocument, remap: dict[EntityID, EntityID]) -> None:
        merge_entities(document, remap, merge_fn=EntityGraphRemapper.merge_entity)
